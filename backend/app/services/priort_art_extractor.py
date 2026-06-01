import logging
from typing import Any
import httpx
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)


async def fetch_patent_data(patent_number: str) -> dict[str, Any] | dict[str, str]:
    """Fetch patent details using httpx with chunked streaming for large payloads."""

    if not patent_number:
        return {"error": "Missing or invalid 'patent_number' argument"}

    url = f"{settings.PATENT_API_BASE_URL}/patent/{patent_number.strip().upper()}"
    logger.debug(f"[EXTRACTOR] Target URL: {url}")

    max_retries = 6
    base_delay = 2

    for attempt in range(max_retries):
        try:
            print("Gooing for patent")
            logger.info(f"[EXTRACTOR] Fetching {patent_number} (Attempt {attempt+1}/{max_retries})")
            # Use streaming to download large patent descriptions in chunks
            # This prevents 'peer closed connection' errors on 1MB+ payloads
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0),
                follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers={"Connection": "close"}) as response:
                    if response.status_code == 200:
                        logger.debug(f"[EXTRACTOR] Connection established for {patent_number}, reading stream...")
                        # Read all chunks until the full body is received
                        content = await response.aread()
                        logger.info(f"[EXTRACTOR] Successfully downloaded {len(content)} bytes for {patent_number}")
                        data = response.json()

                        
                        # classification_codes = [
                        #     c["code"] for c in data.get("classifications", []) if "code" in c
                        # ]
                        result = {
                            "patent_number": patent_number,
                            "title": data.get("title", ""),
                            "assignees": data.get("assignees", []),
                            "structured_claims":data.get("structured_claims",[]),
                            "structured_description":data.get("structured_description",[]),
                            "abstract": data.get("abstract"),
                            "classifications": data.get("classifications", []),
                        }
                        return result

                    elif response.status_code in [502, 503, 504]:
                        logger.warning(f"Attempt {attempt + 1} failed with status {response.status_code}. Retrying...")
                        await asyncio.sleep(base_delay * (2 ** attempt))

                    else:
                        body = await response.aread()
                        logger.error(f"HTTP error: {response.status_code}, message: {body.decode('utf-8', errors='replace')[:200]}")
                        return {"error_message": f"HTTP error {response.status_code}"}

        except httpx.RequestError as e:
            logger.warning(f"Attempt {attempt + 1} failed with network error: {e}. Retrying...")
            await asyncio.sleep(base_delay * (2 ** attempt))

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"error_message": f"Unexpected error: {str(e)}"}

    return {"error_message": f"Failed to fetch patent data after {max_retries} attempts"}

import httpx
import logging
import re
from typing import Dict, Any
from bs4 import BeautifulSoup
from app.core.config import settings
from app.services.ingestion import enrich_patent_with_llm

logger = logging.getLogger(__name__)

class PatentFetchService:

    def extract_section(self, structured_description, target_heading):
        """
        Extract section content from structured_description.
        """

        collecting = False
        collected_paragraphs = []

        for item in structured_description:

            # Parse HTML fragment
            soup = BeautifulSoup(item, "html.parser")

            # Check heading
            heading = soup.find("heading")

            if heading:
                heading_text = heading.get_text(strip=True).upper()

                # Start collecting
                if heading_text == target_heading.upper():
                    collecting = True
                    continue

                # Stop when next heading appears
                elif collecting:
                    break

            # Collect paragraphs
            if collecting:
                text = soup.get_text(" ", strip=True)

                if text:
                    collected_paragraphs.append(text)

        return "\n\n".join(collected_paragraphs)

    async def fetch_patent(self, patent_number: str, skip_llm: bool = False) -> Dict[str, Any]:
        # Standardize search query format

        logger.info("Fetching google patent....")
        clean_number = re.sub(r'[^a-zA-Z0-9]', '', patent_number).upper()        
        # Resilient fetch with retry logic (5 attempts, 30s timeout, exponential backoff)
        import asyncio
        max_retries = 5
        base_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching patent {patent_number} (Attempt {attempt + 1}/{max_retries})")
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
                    follow_redirects=True
                ) as client:
                    res = await client.get(f"{settings.PATENT_API_BASE_URL}/patent/{patent_number}")

                    if res.status_code == 200:
                        # Clean abstract and claims patterns if found
                        data = res.json()
                        structured_description = data.get("structured_description", [])

                        background = self.extract_section(
                            structured_description,
                            "BACKGROUND"
                        )

                        brief_summary = self.extract_section(
                            structured_description,
                            "BRIEF SUMMARY"
                        )

                        raw_data = {
                            "claims": data.get("claims", []),
                            "structured_summary": {
                                "background": background,
                                "brief_summary": brief_summary
                            }
                        }

                        assignees = data.get("assignees", [])
                        assignee = ", ".join(assignees) if isinstance(assignees, list) else assignees

                        if skip_llm:
                            structured_summary = {
                                "core_inventive_concept": "",
                                "problem_solution_mapping": {"problem": "", "solution": ""},
                                "novelty_points": []
                            }
                            claims = raw_data.get("claims", [])
                        else:
                            enriched = await enrich_patent_with_llm(raw_data)
                            
                            # Guard against LLM returning empty string or None
                            structured_summary = enriched.get("structured_summary")
                            if not isinstance(structured_summary, dict):
                                structured_summary = {
                                    "core_inventive_concept": "",
                                    "problem_solution_mapping": {"problem": "", "solution": ""},
                                    "novelty_points": []
                                }
    
                            claims = enriched.get("claims")
                            if not isinstance(claims, list):
                                claims = []
                        return {
                            "patent_number": patent_number,
                            "title": data.get("title", ""),
                            "assignee": assignee,
                            "abstract": data.get("abstract", ""),
                            "claims": claims,
                            "structured_summary": structured_summary
                        }

                    elif res.status_code in [502, 503, 504]:
                        logger.warning(f"Attempt {attempt + 1} got status {res.status_code}. Retrying...")
                        await asyncio.sleep(base_delay * (2 ** attempt))
                        continue

                    else:
                        # Non-retryable HTTP error (e.g. 404, 400)
                        raise ValueError(
                            f"Patent API returned HTTP {res.status_code} for {patent_number}"
                        )

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed with network error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    continue
                else:
                    raise ValueError(
                        f"Failed to fetch patent {patent_number} after {max_retries} attempts: {e}"
                    )

            except Exception as e:
                logger.exception(f"Unexpected error fetching patent {patent_number}")
                raise ValueError(f"Failed to fetch patent {patent_number}: {e}")

        # Should never reach here, but safety net
        raise ValueError(f"Failed to fetch patent {patent_number} after {max_retries} attempts")


    

patent_fetch_service = PatentFetchService()

# ingestion.py
import json
import re
import logging
from app.utils.llm_client import llm_client

logger = logging.getLogger(__name__)

async def enrich_patent_with_llm(raw_patent: dict) -> dict:
    # At the top of enrich_patent_with_llm, before building the prompt
    background = raw_patent.get('structured_summary', {}).get('background', '') or ''
    # print("BACKGROUND", background)
    brief_summary = raw_patent.get('structured_summary', {}).get('brief_summary', '') or ''
    # print("BRIEF SUMMARY", brief_summary)
    claims = raw_patent.get('claims') or []
    # print("CLAIMS", claims)

    prompt = f"""You are a patent analysis expert. Given the following raw patent fields, return a structured JSON.

Input:
- Claims: {json.dumps(claims, indent=2)}
- Background: {background or 'Not available'}
- Brief Summary: {brief_summary or 'Not available'}
...

Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
  "claims": [
    {{
      "claim_number": 1,
      "claim_type": "independent or dependent",
      "claim_text": "<claim text>"
    }}
  ],
  "structured_summary": {{
    "core_inventive_concept": "<one sentence describing the core invention>",
    "problem_solution_mapping": {{
      "problem": "<problem the patent solves>",
      "solution": "<how it solves it>"
    }},
    "novelty_points": ["<point 1>", "<point 2>", "<point 3>"]
  }}
}}"""

    response_text = await llm_client.chat_completion(
        prompt=prompt,
        system_prompt="You are a patent analysis expert. Always respond with valid JSON only.",
    )

    # ---------- Robust JSON extraction ----------
    response_text = response_text.strip()

    # 1. Strip markdown code fences: ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
    if fence_match:
        response_text = fence_match.group(1).strip()
    
    # 2. Extract the outermost JSON object in case the LLM added extra text
    obj_match = re.search(r"\{[\s\S]*\}", response_text)
    if obj_match:
        response_text = obj_match.group(0)

    # 3. Remove trailing commas before } or ] (common LLM mistake)
    response_text = re.sub(r",\s*([}\]])", r"\1", response_text)

    enriched = json.loads(response_text)
    return enriched
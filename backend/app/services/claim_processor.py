import asyncio
from typing import List, Dict
from app.utils.llm_client import llm_client
from app.utils.validation import clamp_weight
from app.utils.rate_limit import limited_call
from app.models.claim import Claim
from app.models.mapping import ClaimElement
from app.database import SessionLocal
from sqlalchemy import select, delete

# Service function to process a list of claim ids and assign weights via LLM
async def split_claims_via_llm(project_id: str, claim_ids: List[str]) -> Dict[str, List[Dict]]:
    """Return a mapping claim_id -> list of element dicts with weight.
    Each element dict: {"element_id": str, "text": str, "weight": float}
    """
    results: Dict[str, List[Dict]] = {}
    async with SessionLocal() as db:
        for claim_id in claim_ids:
            # fetch claim text
            result = await db.execute(select(Claim).where(Claim.id == claim_id))
            claim: Claim = result.scalars().first()
            if not claim:
                continue
            prompt = f"""You are a senior patent attorney conducting invalidity analysis.

Analyze the following patent claim. Extract each distinct claim limitation as a separate element.

For each element, assign an independent invalidation difficulty score (0-100) based on:
- How technically specific and narrow the limitation is
- How rare or novel the technical concept is
- How hard it would be to find prior art that teaches this specific limitation
- Whether it is preamble (lower score) or a core structural/functional limitation (higher score)
- Whether it requires a rare combination of prior art references to challenge

Scoring guide:
  70-100 : Highly specific, novel, technically unique – very difficult to invalidate
  30-69  : Moderately specific – some prior art risk
  1-29   : Generic, well-known, or preamble – easy to find prior art

IMPORTANT:
- Each element is scored independently. Scores do NOT need to sum to 100.
- No single score may exceed 100.
- Do NOT include your reasoning in the output. Think internally, then return only the JSON.
- Return ONLY valid JSON, no markdown, no explanation.

Output format:
{{"elements": [{{"element_id": "1", "text": "<exact limitation text>", "weight": <number>}}]}}

Claim text:
{claim.claim_text}"""
            # LLM call with retries
            response_text = await limited_call(lambda: llm_client.chat_completion(
                prompt,
                system_prompt="You are a senior patent attorney. Return only valid JSON, no markdown.",
                use_reasoning=False,
                temperature=0.1
            ))
            try:
                import json
                import re
                raw = response_text.strip()
                
                # 1. Strip markdown fences
                fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                if fence_match:
                    raw = fence_match.group(1).strip()
                
                # 2. Extract JSON object
                obj_match = re.search(r"\{[\s\S]*\}", raw)
                if obj_match:
                    raw = obj_match.group(0)
                    
                # 3. Fix trailing commas
                raw = re.sub(r",\s*([}\]])", r"\1", raw)
                
                parsed = json.loads(raw)
                elements = parsed.get("elements", [])
            except Exception as e:
                raise ValueError(f"Failed to parse LLM response for claim {claim_id}: {e}")
            # Mathematically normalize weights using Largest Remainder Method so they sum to exactly 100 integers
            raw_weights = [clamp_weight(el.get("weight", 0)) for el in elements]
            total_weight = sum(raw_weights)
            
            if total_weight > 0:
                exact_percentages = [(w / total_weight) * 100.0 for w in raw_weights]
                integer_parts = [int(p) for p in exact_percentages]
                remainders = [exact_percentages[i] - integer_parts[i] for i in range(len(elements))]
                
                missing_points = 100 - sum(integer_parts)
                
                # Give missing points to the elements with the largest remainders
                indices_by_remainder = sorted(range(len(elements)), key=lambda i: remainders[i], reverse=True)
                for i in range(missing_points):
                    integer_parts[indices_by_remainder[i]] += 1
                    
                for i, el in enumerate(elements):
                    el["weight"] = float(integer_parts[i])
            else:
                # Fallback if AI gave 0 for everything
                base_val = 100 // len(elements) if elements else 0
                missing_points = 100 - (base_val * len(elements))
                for i, el in enumerate(elements):
                    el["weight"] = float(base_val + (1 if i < missing_points else 0))
            
            # Clear existing elements to avoid primary/unique key conflicts
            await db.execute(delete(ClaimElement).where(ClaimElement.claim_id == claim_id))
            
            # persist to DB as ClaimElement
            for el in elements:
                weight = el.get("weight", 0)
                if weight >= 30:
                    priority = "Critical"
                elif weight >= 20:
                    priority = "High"
                elif weight >= 10:
                    priority = "Medium"
                else:
                    priority = "Low"
                    
                label_with_priority = f"Limitation {el.get('element_id')}:::{priority}"
                
                ce = ClaimElement(
                    claim_id=claim_id,
                    element_id=el.get("element_id"),
                    label=label_with_priority,
                    text=el.get("text", ""),
                    weight=weight
                )
                db.add(ce)
            await db.commit()
            results[claim_id] = elements
    return results

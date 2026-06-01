import logging
import json
from typing import Any, Dict, List, Optional, Tuple

from app.embedding.qdrant_service import search_element_in_prior_art
from app.embedding.text_utils import normalize_patent_number, patent_numbers_match
from app.utils.llm_client import llm_client

logger = logging.getLogger(__name__)


def _location_from_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
    """Build para_ref and fig_ref strictly from Qdrant chunk metadata."""
    ptype = payload.get("type", "")
    if ptype == "description_chunk":
        para = f"Paragraph {payload.get('paragraph_number', '')}"
        figs = payload.get("figure_refs") or []
        fig = ", ".join(str(f) for f in figs) if payload.get("has_figure") and figs else ""
        return para.strip(), fig
    if ptype == "abstract":
        return "Abstract", ""
    if ptype in ("claim", "claim_element"):
        return f"Claim {payload.get('claim_number', '')}".strip(), ""
    return "", ""


def _citation_from_payload(payload: Dict[str, Any], max_len: int = 500) -> str:
    text = (payload.get("text") or "").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


class MappingEngineService:
    async def compare_element_to_patent(
        self,
        element_text: str,
        element_id: str,
        patent_abstract: str,
        patent_number: str,
        project_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        prior_art = normalize_patent_number(patent_number) or patent_number.strip()

        results = await search_element_in_prior_art(
            element_text,
            [patent_number, prior_art],
            project_id=project_id,
            user_id=user_id,
            top_k=5,
        )

        valid_payloads: List[Dict[str, Any]] = []
        snippets: List[str] = []
        max_score = 0.0
        best_payload: Optional[Dict[str, Any]] = None

        for res in results:
            score = getattr(res, "score", 0.0) or 0.0
            payload = res.payload or {}
            if not patent_numbers_match(payload.get("patent_number", ""), patent_number, prior_art):
                continue
            valid_payloads.append(payload)
            if score > max_score:
                max_score = score
                best_payload = payload

            meta_parts = [f"patent={payload.get('patent_number', '')}"]
            if payload.get("type"):
                meta_parts.append(str(payload["type"]))
            if payload.get("claim_number"):
                meta_parts.append(f"Claim:{payload['claim_number']}")
            if payload.get("paragraph_number"):
                meta_parts.append(f"Para:{payload['paragraph_number']}")
            if payload.get("has_figure"):
                figs = ",".join(payload.get("figure_refs") or [])
                meta_parts.append(f"Fig:{figs}" if figs else "Fig:True")
            meta_str = " | ".join(meta_parts)
            snippets.append(f"[{meta_str} score={score:.2f}]: {payload.get('text', '')}")

        if not valid_payloads or not best_payload:
            return {
                "classification": "N",
                "cited_passage": "",
                "para_ref": "",
                "fig_ref": "",
                "rationale": (
                    f"No passages indexed for prior art {prior_art} in this project. "
                    "Embed this reference patent before running analysis."
                ),
                "claim_number": "",
                "claim_independence": None,
                "element_id": "",
                "paragraph_number": "",
                "has_figure": None,
            }

        cited_passage = _citation_from_payload(best_payload)
        para_ref, fig_ref = _location_from_payload(best_payload)
        snippets_text = "\n\n".join(snippets)

        prompt = f"""You are an expert patent attorney comparing a subject claim element to ONE prior art patent.

Prior art patent (ONLY source allowed): {prior_art}
Subject claim element: {element_text}

Retrieved passages from {prior_art} (use ONLY these; do not invent locations or quotes):
{snippets_text}

Rules:
- Base classification ONLY on the retrieved passages above from {prior_art}.
- Do NOT cite the subject patent or any other patent.
- Do NOT invent paragraph numbers, claim numbers, or figure numbers not present in the snippets.
- If passages do not support disclosure, classification must be "N".

Tasks:
1. Classification: "Y" (fully disclosed), "P" (partially), or "N" (not disclosed).
2. One or two sentence rationale referencing {prior_art}.

Output ONLY valid JSON:
{{
  "classification": "Y" | "P" | "N",
  "rationale": "..."
}}
"""

        classification = "N"
        rationale = "Rationale generation failed."

        try:
            resp = await llm_client.chat_completion(prompt, use_reasoning=False)
            resp = resp.strip()
            if resp.startswith("```json"):
                resp = resp[7:-3].strip()
            elif resp.startswith("```"):
                resp = resp[3:-3].strip()
            rationale_json = json.loads(resp)
            classification = rationale_json.get("classification", "N")
            rationale = rationale_json.get("rationale", rationale)
        except Exception as e:
            logger.error("LLM rationale generation failed: %s", e)

        if classification not in ("Y", "P", "N"):
            if max_score > 0.8:
                classification = "Y"
            elif max_score > 0.6:
                classification = "P"
            else:
                classification = "N"

        if classification == "N" and max_score > 0.75:
            classification = "P"

        ptype = best_payload.get("type", "")
        claim_number = str(best_payload.get("claim_number", "") or "")
        claim_independence = best_payload.get("is_independent")
        element_id_opt = str(best_payload.get("element_id", "") or "")
        paragraph_number = str(best_payload.get("paragraph_number", "") or "")
        has_figure = best_payload.get("has_figure")

        return {
            "classification": classification,
            "cited_passage": cited_passage,
            "para_ref": para_ref,
            "fig_ref": fig_ref,
            "rationale": rationale,
            "claim_number": claim_number,
            "claim_independence": claim_independence,
            "element_id": element_id_opt,
            "paragraph_number": paragraph_number,
            "has_figure": has_figure,
        }


mapping_engine_service = MappingEngineService()

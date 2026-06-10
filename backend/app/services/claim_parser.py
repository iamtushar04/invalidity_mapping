import logging
import string
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ClaimParserService:
    async def segment_claim(self, claim_text: str, claim_number: int) -> List[Dict[str, Any]]:
        logger.info(f"Dynamically parsing Claim {claim_number}")
        
        # 1. Clean up newlines and spaces
        text = " ".join([line.strip() for line in claim_text.splitlines() if line.strip()])
        
        # 2. Split the claim by semicolons (standard patent limitation separator)
        # It safely ignores trailing 'and' or 'or' that follow semicolons
        parts = re.split(r';\s*(?:and\s+|or\s+)?', text)
        
        final_parts = []
        for p in parts:
            p_clean = p.strip()
            if not p_clean:
                continue
                
            # 3. Separate the Preamble from the first limitation if 'comprising:' is found
            if "comprising:" in p_clean:
                subparts = p_clean.split("comprising:")
                final_parts.append(subparts[0].strip() + " comprising:")
                if subparts[1].strip():
                    final_parts.append(subparts[1].strip())
            elif "comprising" in p_clean and "comprising" not in final_parts:
                 # sometimes it's just 'comprising' without a colon
                 subparts = p_clean.split("comprising", 1)
                 final_parts.append(subparts[0].strip() + " comprising")
                 if subparts[1].strip():
                     final_parts.append(subparts[1].strip())
            else:
                final_parts.append(p_clean)
                
        # Fallback if parsing completely fails
        if not final_parts:
            final_parts = [claim_text]

        # 4. Package them into the exact format the UI expects
        results = []
        base_weight = round(100.0 / len(final_parts), 2)
        
        for idx, part in enumerate(final_parts):
            # Generate 1A, 1B, 1C
            letter = string.ascii_uppercase[idx % 26]
            if idx >= 26:
                letter = string.ascii_uppercase[(idx // 26) - 1] + letter
                
            # Label the first piece as the Preamble
            label = "Preamble" if idx == 0 else f"Limitation {idx}"
            
            results.append({
                "element_id": f"{claim_number}{letter}",
                "label": label,
                "text": part,
                "weight": base_weight
            })
            
        return results

claim_parser_service = ClaimParserService()

import json
from app.services.recurssive_splitter import chunk_full_claim

def convert_claims(data: dict) -> list[dict]:

    converted_claims = []
    metadata = {
                "patent_number": data.get("patent_number"),
                "title": data.get("title"),
                "classifications": data.get("classifications", [])
    }
    converted_claims.append({
        "metadata": metadata
    })
    
    structured_claims = data.get("structured_claims", [])


    for claim in structured_claims:

        claim_number = claim.get("claim_number", "0")

        elements = []

        for idx, el in enumerate(claim.get("elements", []), start=1):

            elements.append({
                "element_id": f"C{claim_number}-E{idx}",
                "text": el.get("text", "").strip(),
                "level": el.get("level", 0)
            })

        converted_claims.append({
            "claim_number": claim_number,
            "is_independent": claim.get("is_independent", False),
            "full_text": chunk_full_claim(claim.get("claim_text", "").strip()),
            "elements": elements,
        })
    return converted_claims






# with open("patent.json", "r", encoding="utf-8") as f:
#     data = json.load(f)
    


# claims = convert_claims(data)
# # print(claims)

# with open("claims.json", "w", encoding="utf-8") as f:
#     json.dump(claims, f, indent=2, ensure_ascii=False)
#     print("Claims stored successfully")



def get_abstract(data: dict) -> dict:
    return {
        "abstract": data.get("abstract", "").strip(),
        "metadata":{
            "patent_number": data.get("patent_number"),
            "title": data.get("title"),
            "classifications": data.get("classifications", [])
        }
    }

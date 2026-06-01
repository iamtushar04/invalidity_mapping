
from bs4 import BeautifulSoup
import re
import json

# pyrefly: ignore [missing-import]
from app.services.preprocess import normalize_text


def process_structured_description(
    structured_description,
    patent_number,
    title,
    classifications
):

    description_chunks = []

    # =====================================================
    # GLOBAL METADATA
    # =====================================================

    description_chunks.append({
        "metadata": {
            "patent_number": patent_number,
            "title": title,
            "classifications": classifications
        }
    })

    # =====================================================
    # PROCESS EACH PARAGRAPH
    # =====================================================

    for idx, raw_html in enumerate(structured_description, start=1):

        soup = BeautifulSoup(raw_html, "html.parser")

        div = soup.find("div")

        if not div:
            continue

        # =====================================================
        # PARAGRAPH IDS
        # =====================================================

        paragraph_id = (
            div.get("id")
            or f"DESC-{idx}"
        )

        paragraph_number = (
            div.get("num")
            or div.get("paragraph-number")
            or str(idx)
        )

        # =====================================================
        # EXTRACT TEXT
        # =====================================================

        text = div.get_text(" ", strip=True)

        text = normalize_text(text)

        if not text:
            continue

        # =====================================================
        # DETECT FIGURE REFERENCES
        # =====================================================

        figure_refs = re.findall(
            r"FIG\.?\s*\d+[A-Z]?",
            text,
            flags=re.IGNORECASE
        )

        figure_refs = list(set(figure_refs))

        has_figure = len(figure_refs) > 0

        # =====================================================
        # DETECT FIGURE CAPTION PARAGRAPH
        # =====================================================

        is_figure_caption = bool(
            re.match(
                r"^\s*FIG\.?\s*\d+[A-Z]?",
                text,
                flags=re.IGNORECASE
            )
        )

        # =====================================================
        # EXTRACT IMAGE / FIGURE-CALLOUT DATA
        # =====================================================

        figure_callouts = soup.find_all("figure-callout")

        images = []

        for fig in figure_callouts:

            images.append({
                "figure_id": fig.get("id"),
                "label": fig.get("label"),
                "filename": fig.get("filenames")
            })

        # =====================================================
        # OPTIONAL:
        # SKIP PURE FIGURE INDEX PARAGRAPHS
        # =====================================================

        # Uncomment if you do NOT want to embed figure captions

        # if is_figure_caption:
        #     continue

        # =====================================================
        # FINAL PAYLOAD
        # =====================================================

        description_chunks.append({

            "type": "description_chunk",

            "chunk_id": paragraph_id,

            "paragraph_number": paragraph_number,

            "text": text,

            # -----------------------------------------
            # Figure metadata
            # -----------------------------------------

            "has_figure": has_figure,

            "figure_refs": figure_refs,

            "is_figure_caption": is_figure_caption,

            # -----------------------------------------
            # Image metadata
            # -----------------------------------------

            "has_images": len(images) > 0,

            "images": images
        })

    return description_chunks



# with open("patent.json", "r", encoding="utf-8") as f:
#     patent_data = json.load(f)


# description_chunks = process_structured_description(
#     structured_description=patent_data["structured_description"],
#     patent_number=patent_data["patent_number"],
#     title=patent_data["title"],
#     classifications=patent_data["classifications"]
# )


# with open("description_chunks.json", "w", encoding="utf-8") as f:

#     json.dump(
#         description_chunks,
#         f,
#         indent=4,
#         ensure_ascii=False
#     )

# print(f"\n✅ Processed {len(description_chunks)} chunks")
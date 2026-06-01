import os
import re
import uuid
import json

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)

from sentence_transformers import (
    SentenceTransformer
)

# =========================================================
# LOAD FILES
# =========================================================

with open("patent_metadata_abstract.json", "r", encoding="utf-8") as f:
    abstract_data = json.load(f)

with open("claims.json", "r", encoding="utf-8") as f:
    claims_data = json.load(f)

with open(
    "description_chunks.json",
    "r",
    encoding="utf-8"
) as f:
    description_data = json.load(f)

# =========================================================
# GLOBAL METADATA
# =========================================================

metadata = claims_data[0]["metadata"]

patent_number = metadata["patent_number"]

title = metadata["title"]

classifications = metadata.get(
    "classifications",
    []
)

cpc_codes = [
    c["code"]
    for c in classifications
]

# =========================================================
# QDRANT
# =========================================================

client = QdrantClient(
    url=os.getenv("QDRANT_URL")
)

COLLECTION_NAME = "testing_patent1"

model = SentenceTransformer(
    "BAAI/bge-large-en-v1.5"
)

VECTOR_SIZE = 1024

# =========================================================
# CREATE COLLECTION
# =========================================================

collections = [
    c.name
    for c in client.get_collections().collections
]

if COLLECTION_NAME not in collections:

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE
        )
    )

# =========================================================
# HELPERS
# =========================================================

def generate_uuid():
    return str(uuid.uuid4())


def normalize_text(text):

    if not text:
        return ""

    if isinstance(text, list):
        text = " ".join(text)

    # Remove leading claim number
    text = re.sub(
        r"^\s*\d+\.\s*",
        "",
        text
    )

    text = " ".join(text.split())

    return text.strip()


def should_skip_embedding(text):

    """
    Skip low-value figure captions.
    """

    text_lower = text.lower()

    if (
        text_lower.startswith("fig.")
        and len(text.split()) < 25
    ):
        return True

    return False


def create_embedding(text):

    normalized_text = normalize_text(text)

    return model.encode(
        normalized_text,
        normalize_embeddings=True
    ).tolist()


# =========================================================
# DEDUP CHECK
# =========================================================

existing = client.scroll(
    collection_name=COLLECTION_NAME,
    scroll_filter=None,
    limit=1,
    with_payload=True
)[0]

already_exists = any(
    p.payload.get("patent_number")
    == patent_number
    for p in existing
)

if already_exists:

    print(
        f"\n⚠ Patent already exists: "
        f"{patent_number}"
    )

    exit()

# =========================================================
# POINTS
# =========================================================

points = []

# =========================================================
# ABSTRACT
# =========================================================

abstract_text = normalize_text(
    abstract_data["abstract"]
)

abstract_vector = create_embedding(
    abstract_text
)

points.append(
    PointStruct(
        id=generate_uuid(),

        vector=abstract_vector,

        payload={

            "doc_id":
                f"{patent_number}-ABSTRACT",

            "patent_number":
                patent_number,

            "type":
                "abstract",

            "text":
                abstract_text
        }
    )
)

# =========================================================
# CLAIMS
# =========================================================

for claim in claims_data:

    if "claim_number" not in claim:
        continue

    claim_number = claim["claim_number"]

    is_independent = claim["is_independent"]

    full_text = normalize_text(
        claim["full_text"]
    )

    # -----------------------------------------------------
    # FULL CLAIM
    # -----------------------------------------------------

    full_claim_vector = create_embedding(
        full_text
    )

    points.append(
        PointStruct(
            id=generate_uuid(),

            vector=full_claim_vector,

            payload={

                "doc_id":
                    f"{patent_number}"
                    f"-CLAIM-{claim_number}",

                "patent_number":
                    patent_number,

                "type":
                    "full_claim",

                "claim_number":
                    claim_number,

                "is_independent":
                    is_independent,

                "text":
                    full_text
            }
        )
    )

    # -----------------------------------------------------
    # CLAIM ELEMENTS
    # -----------------------------------------------------

    for element in claim.get(
        "elements",
        []
    ):

        element_text = normalize_text(
            element["text"]
        )

        vector = create_embedding(
            element_text
        )

        points.append(
            PointStruct(
                id=generate_uuid(),

                vector=vector,

                payload={

                    "doc_id":
                        f"{patent_number}"
                        f"-{element['element_id']}",

                    "patent_number":
                        patent_number,

                    "type":
                        "claim_element",

                    "claim_number":
                        claim_number,

                    "is_independent":
                        is_independent,

                    "element_id":
                        element["element_id"],

                    "level":
                        element["level"],

                    "text":
                        element_text
                }
            )
        )

# =========================================================
# DESCRIPTION CHUNKS
# =========================================================

for chunk in description_data:

    # Skip metadata object
    if "type" not in chunk:
        continue

    chunk_text = normalize_text(
        chunk["text"]
    )

    # Skip useless figure captions
    if should_skip_embedding(
        chunk_text
    ):
        continue

    vector = create_embedding(
        chunk_text
    )

    points.append(
        PointStruct(
            id=generate_uuid(),

            vector=vector,

            payload={

                "doc_id":
                    f"{patent_number}"
                    f"-{chunk['chunk_id']}",

                "patent_number":
                    patent_number,

                "type":
                    "description_chunk",

                "chunk_id":
                    chunk["chunk_id"],

                "paragraph_number":
                    chunk["paragraph_number"],

                "has_figure":
                    chunk.get(
                        "has_figure",
                        False
                    ),

                "figure_refs":
                    chunk.get(
                        "figure_refs",
                        []
                    ),

                "is_figure_caption":
                    chunk.get(
                        "is_figure_caption",
                        False
                    ),

                "has_images":
                    chunk.get(
                        "has_images",
                        False
                    ),

                "images":
                    chunk.get(
                        "images",
                        []
                    ),

                "text":
                    chunk_text
            }
        )
    )

# =========================================================
# UPSERT
# =========================================================

client.upsert(
    collection_name=COLLECTION_NAME,
    points=points
)

print(
    f"\n✅ Inserted "
    f"{len(points)} vectors"
)

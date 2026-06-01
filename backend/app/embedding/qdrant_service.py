"""Qdrant embedding service for prior‑art patents.

- Uses the local SentenceTransformer model ``BAAI/bge-large-en-v1.5`` (1024‑dim).
- Stores vectors in collection ``prior_art_patents_1``.
- Deduplicates by ``project_id`` + ``patent_number`` within that collection.
- Handles four payload types: ``abstract``, ``claim``, ``claim_element`` and ``description_chunk``.
"""
from qdrant_client.models import VectorParams, Distance
import os
from typing import Any, Dict, List
import uuid
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from app.core.config import settings
from app.embedding.text_utils import (
    normalize_text,
    should_skip_embedding,
    normalize_patent_number,
    patent_number_variants,
    patent_numbers_match,
)

# ---------------------------------------------------------------------------
# Global singletons – loaded once per process
# ---------------------------------------------------------------------------

print("Getting Data From")
_MODEL = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cpu")
_QDRANT_URL = getattr(settings, "QDRANT_URL", None) or os.getenv("QDRANT_URL")
if not _QDRANT_URL:
    raise ValueError("QDRANT_URL environment variable is missing")
_CLIENT = QdrantClient(url=_QDRANT_URL)

_COLLECTION_NAME = "matrix_mapping_wissen"
_VECTOR_SIZE = 1024

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def _ensure_collection() -> None:
    """Create collection if missing."""
    
    try:
        _CLIENT.get_collection(_COLLECTION_NAME)
        print(f"Collection '{_COLLECTION_NAME}' already exists")
    except Exception:
        print(f"Creating collection '{_COLLECTION_NAME}'")
        _CLIENT.create_collection(
            collection_name=_COLLECTION_NAME,
            vectors_config=VectorParams(
                size=_VECTOR_SIZE,
                distance=Distance.COSINE
            ),
        )

def _search_vectors(query_vector: List[float], search_filter: Any = None, limit: int = 5) -> List[Any]:
    """Perform a vector search using Qdrant client.

    Supports both the modern API (query_points, qdrant-client >= 1.7) and the
    legacy API (search, qdrant-client < 1.7).  Falls back to scroll + manual
    cosine if neither is available.
    """
    # ── Modern API (qdrant-client >= 1.7) ─────────────────────────────────
    if hasattr(_CLIENT, "query_points"):
        from qdrant_client.models import ScoredPoint
        response = _CLIENT.query_points(
            collection_name=_COLLECTION_NAME,
            query=query_vector,
            query_filter=search_filter,
            limit=limit,
            with_payload=True,
        )
        # query_points returns a QueryResponse; results are in .points
        return response.points

    # ── Legacy API (qdrant-client < 1.7) ──────────────────────────────────
    if hasattr(_CLIENT, "search"):
        return _CLIENT.search(
            collection_name=_COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=limit,
            with_payload=True,
        )

    # ── Last-resort: scroll + manual cosine ───────────────────────────────
    records, _ = _CLIENT.scroll(
        collection_name=_COLLECTION_NAME,
        scroll_filter=search_filter,
        limit=limit * 10,
        with_payload=True,
        with_vectors=True,
    )
    def cosine(a, b):
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
    scored = []
    for point in records:
        try:
            score = cosine(query_vector, point.vector)
            point.score = score
            scored.append(point)
        except Exception:
            continue
    scored.sort(key=lambda p: getattr(p, "score", 0), reverse=True)
    return scored[:limit]


def _embed_text(text: str) -> List[float]:
    """Return the embedding vector for *text* using the loaded model."""
    # normalize_embeddings=True is required for BAAI/bge models with cosine distance
    return _MODEL.encode([normalize_text(text)], normalize_embeddings=True)[0].tolist()

def _skip(text: Any) -> bool:
    """Return ``True`` if the supplied text should be ignored for embedding."""
    if isinstance(text, (list, tuple)):
        text = " ".join(text)
    return should_skip_embedding(str(text))


def _patent_number_variants(*numbers: str) -> List[str]:
    """Return deduplicated patent number forms (original and hyphenless)."""
    return list(patent_number_variants(*numbers))

# ---------------------------------------------------------------------------
# Public API – called from the FastAPI route
# ---------------------------------------------------------------------------
async def embed_patent(
    patent_number: str,
    abstract_data: Dict[str, Any],
    claims_data: List[Dict[str, Any]],
    description_data: List[Dict[str, Any]],
    project_id: str,
    user_id: str | None = None,
) -> None:
    """Embed a single patent and upsert all vectors into Qdrant.

    The function is **idempotent** per project – if any point with this
    ``project_id`` and ``patent_number`` already exists, the function returns early.
    """
    _ensure_collection()

    canonical_patent = normalize_patent_number(patent_number)

    # ---- 1️⃣ Deduplication (scoped to project + user + patent) ----------------
    # user_id is included so that a re-embed with a different user_id is never
    # silently skipped — the search filter also requires user_id to match.
    records, _ = _CLIENT.scroll(
        collection_name=_COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="project_id",
                    match=MatchValue(value=str(project_id)),
                ),
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=str(user_id)),
                ),
                FieldCondition(
                    key="patent_number",
                    match=MatchValue(value=canonical_patent),
                ),
            ]
        ),
        limit=1,
    )

    if records:
        print(f"{canonical_patent} already embedded in project {project_id}")
        return

    points: List[PointStruct] = []

    # ---- 2️⃣ Abstract ------------------------------------------------------
    abstract_text = abstract_data.get("abstract", "")
    if not _skip(abstract_text):
        vec = _embed_text(abstract_text)
        payload = {
            "type": "abstract",
            "patent_number": canonical_patent,
            "reference_patent": canonical_patent,
            "user_id": str(user_id),
            "project_id": str(project_id),
            "title": abstract_data.get("metadata", {}).get("title", ""),
            "cpc_codes": [c.get("code") for c in abstract_data.get("metadata", {}).get("classifications", [])],
            "text": abstract_text
        }
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload=payload
        )   )

    # ---- 3️⃣ Claims --------------------------------------------------------
    # ``claims_data`` first element is metadata – skip it.
    for claim in claims_data:
        if claim.get("type") == "metadata":
            continue
        claim_number = claim.get("claim_number")
        claim_text = " ".join(claim.get("full_text", []))
        if _skip(claim_text):
            continue
        vec = _embed_text(claim_text)
        payload = {
            "type": "claim",
            "patent_number": canonical_patent,
            "reference_patent": canonical_patent,
            "user_id": str(user_id),
            "project_id": str(project_id),
            "claim_number": claim_number,
            "is_independent": claim.get("is_independent", False),
            "text": claim_text
        }
        points.append(PointStruct(id=str(uuid.uuid4()), vector=vec, payload=payload))

        # ---- Elements inside the claim -----------------------------------
        for element in claim.get("elements", []):
            el_text = element.get("text", "")
            if _skip(el_text):
                continue
            vec_el = _embed_text(el_text)
            payload_el = {
                "type": "claim_element",
                # ✅ FIX: use canonical_patent (not raw patent_number) so that
                #    patent_number_variants() in the search filter can match it.
                "patent_number": canonical_patent,
                "reference_patent": canonical_patent,
                "user_id": str(user_id),
                "project_id": str(project_id),
                "claim_number": claim_number,
                "is_independent": claim.get("is_independent", False),
                "element_id": element.get("element_id"),  # ✅ FIX: key is "element_id" not "id"
                "level": element.get("level"),
                "text": el_text
            }
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vec_el,
                payload=payload_el
            ))

    # ---- 4️⃣ Description chunks -------------------------------------------
    for chunk in description_data:
        if chunk.get("type") == "metadata":
            continue
        text = chunk.get("text", "")
        if _skip(text):
            continue
        vec = _embed_text(text)
        payload = {
            "type": "description_chunk",
            "patent_number": canonical_patent,
            "reference_patent": canonical_patent,
            "user_id": str(user_id),
            "project_id": str(project_id),
            "chunk_id": chunk.get("chunk_id"),
            "paragraph_number": chunk.get("paragraph_number"),
            "has_figure": chunk.get("has_figure", False),
            "figure_refs": chunk.get("figure_refs", []),
            "has_images": chunk.get("has_images", False),
            "text": text
        }
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload=payload
            )   
        )

    # ---- 5️⃣ Bulk upsert ---------------------------------------------------
    if points:
        _CLIENT.upsert(collection_name=_COLLECTION_NAME, points=points)

async def search_element_in_prior_art(
    element_text: str,
    patent_numbers: List[str],
    project_id: str,
    user_id: str,
    top_k: int = 20,
) -> List[Any]:
    """Search for an element in Qdrant, scoped to project, user, and patent number(s).

    Args:
        element_text: Text of the element to embed and search.
        patent_numbers: Patent identifiers to search (hyphenated and plain forms are OR-matched).
        project_id: Project isolation – only vectors from this project are considered.
        user_id: User isolation – only vectors embedded for this user are considered.
        top_k: Number of nearest neighbours to return.
    """
    _ensure_collection()

    vec = _embed_text(element_text)

    patent_variants = _patent_number_variants(*patent_numbers)
    if not patent_variants:
        return []

    # Build patent OR-filter as nested should inside a wrapping must.
    # Using MinShould at the top level alongside must is unreliable in some
    # Qdrant versions — a nested Filter in a must condition is more portable.
    patent_conditions = [
        FieldCondition(key="patent_number", match=MatchValue(value=num))
        for num in patent_variants
    ]

    if len(patent_conditions) == 1:
        # Single patent — add directly to must
        search_filter = Filter(
            must=[
                FieldCondition(key="project_id", match=MatchValue(value=str(project_id))),
                FieldCondition(key="user_id",    match=MatchValue(value=str(user_id))),
                patent_conditions[0],
            ]
        )
    else:
        # Multiple patents — nest a should-filter inside must
        search_filter = Filter(
            must=[
                FieldCondition(key="project_id", match=MatchValue(value=str(project_id))),
                FieldCondition(key="user_id",    match=MatchValue(value=str(user_id))),
                # Nested filter: at least ONE patent variant must match
                Filter(should=patent_conditions),
            ]
        )

    import asyncio
    raw_results = await asyncio.to_thread(
        _search_vectors,
        vec,           # positional — avoids any to_thread kwarg ambiguity
        search_filter,
        top_k * 3,
    )

    # Secondary Python-level guard: drop hits whose patent_number doesn't match
    filtered = []
    for res in raw_results:
        payload = res.payload or {}
        if patent_numbers_match(payload.get("patent_number", ""), *patent_numbers):
            filtered.append(res)
        if len(filtered) >= top_k:
            break
    return filtered


# End of file

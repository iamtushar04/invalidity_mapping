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
import asyncio
import concurrent.futures
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
import logging

logger = logging.getLogger(__name__)

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
# _MODEL = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cpu")
_MODEL = SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")

def _worker_embed_batch(texts: List[str]) -> List[List[float]]:
    """Worker function to embed a batch of texts using the globally loaded model."""
    from app.embedding.text_utils import normalize_text
    normalized_texts = [normalize_text(t) for t in texts]
    embeddings = _MODEL.encode(normalized_texts, batch_size=64, normalize_embeddings=True)
    return [emb.tolist() for emb in embeddings]

PROCESS_POOL = None

def get_process_pool():
    global PROCESS_POOL
    if PROCESS_POOL is None:
        PROCESS_POOL = concurrent.futures.ProcessPoolExecutor(max_workers=3)
    return PROCESS_POOL

async def async_prewarm_workers():
    """Silently load the SentenceTransformer model into the CPU workers on startup."""
    logger.info("Initializing background pre-warm sequence for CPU workers...")
    pool = get_process_pool()
    loop = asyncio.get_running_loop()
    # Send a dummy embedding task to all workers simultaneously (we have 3 per Uvicorn worker)
    tasks = [loop.run_in_executor(pool, _worker_embed_batch, ["warmup text"]) for _ in range(3)]
    await asyncio.gather(*tasks)
    logger.info("CPU workers successfully pre-warmed and ready for instant embedding!")

_QDRANT_HOST = getattr(settings, "QDRANT_HOST", "localhost")
_QDRANT_PORT = getattr(settings, "QDRANT_PORT", 6333)
_QDRANT_API_KEY = getattr(settings, "QDRANT_API_KEY", "")

_CLIENT = QdrantClient(
    host=_QDRANT_HOST,
    port=_QDRANT_PORT,
    api_key=_QDRANT_API_KEY if _QDRANT_API_KEY else None,
    https=False,
    timeout=3600.0  # 1 hour timeout (effectively waits until done)
)


# _COLLECTION_NAME = "matrix_mapping_wissen"
# _VECTOR_SIZE = 1024
_COLLECTION_NAME = "matrix_mapping_wissen_base"
_VECTOR_SIZE = 768

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
    force_reembed: bool = False,
) -> bool:
    """Embed a single patent and upsert all vectors into Qdrant.

    The function is **idempotent** per project – if any point with this
    ``project_id`` and ``patent_number`` already exists, the function returns early.
    """
    _ensure_collection()

    canonical_patent = normalize_patent_number(patent_number)
    
    logger.info(f"Starting Qdrant vector embedding process for patent {canonical_patent}")
    logger.info("Checking for existing embeddings (Deduplication check)...")

    # ---- 1️⃣ Deduplication (scoped to project + user + patent) ----------------
    if force_reembed:
        logger.info(f"Force re-embed requested for {canonical_patent}. Wiping existing vectors from Qdrant.")
        await asyncio.to_thread(
            _CLIENT.delete,
            collection_name=_COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(key="project_id", match=MatchValue(value=str(project_id))),
                    FieldCondition(key="user_id", match=MatchValue(value=str(user_id))),
                    FieldCondition(key="patent_number", match=MatchValue(value=canonical_patent)),
                ]
            )
        )
    else:
        # user_id is included so that a re-embed with a different user_id is never
        # silently skipped — the search filter also requires user_id to match.
        records, _ = await asyncio.to_thread(
            _CLIENT.scroll,
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
            logger.info(f"Patent {canonical_patent} already embedded in Qdrant for this project. Skipping.")
            return True

    points: List[PointStruct] = []
    texts_to_embed: List[str] = []
    payload_blueprints: List[Dict[str, Any]] = []

    # ---- 2️⃣ Abstract ------------------------------------------------------
    logger.info("Processing abstract embedding...")
    abstract_text = abstract_data.get("abstract", "")
    if not _skip(abstract_text):
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
        texts_to_embed.append(abstract_text)
        payload_blueprints.append(payload)

    # ---- 3️⃣ Claims --------------------------------------------------------
    # ``claims_data`` first element is metadata – skip it.
    logger.info(f"Processing {len(claims_data)} claim entries for embedding...")
    for claim in claims_data:
        if claim.get("type") == "metadata":
            continue
        claim_number = claim.get("claim_number")
        claim_text = " ".join(claim.get("full_text", []))
        if _skip(claim_text):
            continue
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
        texts_to_embed.append(claim_text)
        payload_blueprints.append(payload)

        # ---- Elements inside the claim -----------------------------------
        for element in claim.get("elements", []):
            el_text = element.get("text", "")
            if _skip(el_text):
                continue
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
            texts_to_embed.append(el_text)
            payload_blueprints.append(payload_el)

    # ---- 4️⃣ Description chunks -------------------------------------------
    logger.info(f"Processing {len(description_data)} description chunks for embedding...")
    for chunk in description_data:
        if chunk.get("type") == "metadata":
            continue
        text = chunk.get("text", "")
        if _skip(text):
            continue
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
        texts_to_embed.append(text)
        payload_blueprints.append(payload)

    # ---- Execute Batch Embedding via ProcessPool ---------------------------
    if texts_to_embed:
        logger.info(f"Batch embedding {len(texts_to_embed)} text chunks via Process Pool...")
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(get_process_pool(), _worker_embed_batch, texts_to_embed)
        
        for vec, payload in zip(vectors, payload_blueprints):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload=payload
            ))

    # ---- 5️⃣ Bulk upsert ---------------------------------------------------
    if points:
        logger.info(f"Pushing {len(points)} generated vectors to Qdrant cluster...")
        await asyncio.to_thread(_CLIENT.upsert, collection_name=_COLLECTION_NAME, points=points)
    
    logger.info(f"Successfully finished embedding and upserting patent {canonical_patent}")
    return False

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

    vec = await asyncio.to_thread(_embed_text, element_text)

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

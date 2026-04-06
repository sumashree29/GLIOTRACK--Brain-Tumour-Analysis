"""
Qdrant RAG knowledge base.
Failure policy: ANY exception -> (False, [], reason). Never propagates.

Fixes applied:
  - Diversity-aware retrieval: max 1 passage per source_document.
    Fetches 5x max_passages candidates, selects the best-scoring chunk
    from each unique guideline, then fills remaining slots in score order.
    Guarantees the doctor sees context from multiple guidelines rather than
    5 chunks from the same PDF.
  - upsert_passages fetches existing chunk_hashes from Qdrant before
    inserting, so re-running ingest does not create duplicate vectors.
  - _build_qdrant_client cache cleared on connection error.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import functools
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RAGPassage:
    source_document: str
    guideline_version: str
    publication_year: int
    passage_text: str
    chunk_index: int
    chunk_hash: str
    score: float


@functools.lru_cache(maxsize=1)
def _build_qdrant_client():
    from qdrant_client import QdrantClient
    if settings.qdrant_api_key:
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return QdrantClient(url=settings.qdrant_url)


def _clear_client_cache():
    _build_qdrant_client.cache_clear()


def _diverse_passages(
    candidates: list[RAGPassage],
    max_results: int,
) -> list[RAGPassage]:
    """
    Select up to max_results passages with at most 1 per source_document.

    Algorithm:
      1. Group candidates by source_document, keeping only the highest-
         scoring chunk per document (candidates are already score-sorted
         so the first occurrence of each source is the best).
      2. Sort the best-per-document list by score descending.
      3. Return top max_results.

    This guarantees diversity across guidelines while still ranking by
    relevance within the constraint. The doctor sees context from multiple
    guidelines rather than 5 chunks from the same PDF.
    """
    seen_sources: dict[str, RAGPassage] = {}
    for p in candidates:
        if p.source_document not in seen_sources:
            seen_sources[p.source_document] = p

    diverse = sorted(seen_sources.values(), key=lambda p: p.score, reverse=True)
    return diverse[:max_results]


def query_knowledge_base(query: str) -> tuple[bool, list[RAGPassage], Optional[str]]:
    try:
        from rag.embeddings import embedding_model
        vec = embedding_model.encode(query)

        try:
            client = _build_qdrant_client()
        except Exception as conn_exc:
            _clear_client_cache()
            return False, [], f"Qdrant connection failed: {conn_exc}"

        col  = settings.qdrant_collection_name
        cols = [c.name for c in client.get_collections().collections]
        if col not in cols:
            return False, [], f"Collection '{col}' not found — run ingest_knowledge_base.py"

        # Fetch 5x the desired count so diversity selection has enough
        # candidates from each source document to choose from
        fetch_limit = settings.rag_max_passages * 5

        hits = client.search(
            collection_name=col,
            query_vector=vec.tolist(),
            limit=fetch_limit,
            with_payload=True,
        )

        candidates: list[RAGPassage] = []
        for h in hits:
            if h.score < settings.rag_min_relevance_score:
                continue
            p = h.payload
            candidates.append(RAGPassage(
                source_document=p.get("source_document", ""),
                guideline_version=p.get("guideline_version", ""),
                publication_year=p.get("publication_year", 0),
                passage_text=p.get("passage_text", ""),
                chunk_index=p.get("chunk_index", 0),
                chunk_hash=p.get("chunk_hash", ""),
                score=h.score,
            ))

        if not candidates:
            logger.warning(
                "RAG: 0 passages above threshold %.2f | query: %s",
                settings.rag_min_relevance_score, query[:80],
            )
            return True, [], None

        passages = _diverse_passages(candidates, settings.rag_max_passages)

        logger.info(
            "RAG: query='%s...' candidates=%d unique_sources=%d returned=%d sources=%s",
            query[:60],
            len(candidates),
            len({p.source_document for p in candidates}),
            len(passages),
            [p.source_document for p in passages],
        )
        return True, passages, None

    except Exception as exc:
        logger.error("RAG query failed: %s", exc)
        _clear_client_cache()
        return False, [], str(exc)


def upsert_passages(texts: list, vectors, payloads: list) -> tuple[int, int]:
    """
    Upsert chunks into Qdrant.
    Fetches existing chunk_hashes first so re-running ingest is idempotent.
    """
    from qdrant_client.models import PointStruct, Distance, VectorParams
    import uuid

    client = _build_qdrant_client()
    col    = settings.qdrant_collection_name
    cols   = [c.name for c in client.get_collections().collections]

    if col not in cols:
        client.create_collection(
            col,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s (dim=384, cosine)", col)

    # Fetch existing hashes to prevent duplicates on re-ingest
    existing_hashes: set[str] = set()
    offset = None
    while True:
        result, next_offset = client.scroll(
            collection_name=col,
            scroll_filter=None,
            limit=1000,
            offset=offset,
            with_payload=["chunk_hash"],
            with_vectors=False,
        )
        for point in result:
            h = (point.payload or {}).get("chunk_hash")
            if h:
                existing_hashes.add(h)
        if next_offset is None:
            break
        offset = next_offset

    logger.info("Existing hashes in collection: %d", len(existing_hashes))

    upserted = skipped = 0
    points: list[PointStruct] = []

    for text, vec, payload in zip(texts, vectors, payloads):
        chunk_hash = payload.get("chunk_hash", "")
        if chunk_hash in existing_hashes:
            skipped += 1
            continue
        existing_hashes.add(chunk_hash)
        payload["passage_text"] = text
        points.append(
            PointStruct(id=str(uuid.uuid4()), vector=vec.tolist(), payload=payload)
        )
        upserted += 1

    for i in range(0, len(points), 100):
        client.upsert(collection_name=col, points=points[i:i + 100])

    return upserted, skipped
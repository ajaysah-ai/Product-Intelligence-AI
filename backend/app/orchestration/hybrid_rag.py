from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings.embedder import embed_texts
from app.models import Chunk, Document, Embedding, TempChunk, TempDocument, TempEmbedding

_reranker = None

RRF_K = 60  # standard RRF damping constant
FUSION_POOL_SIZE = 20  # how many candidates each ranker (vector/BM25) contributes before fusion
RERANK_SHORTLIST_SIZE = 15  # how many fused candidates actually go through the cross-encoder


def _get_reranker():
    """Cross-encoder reranker, lazy singleton like the embedding model. Reused
    across requests — construction cost is the same class of expense as
    loading the embedding model in Phase 4. Uses GPU automatically if
    one's available."""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        from app.concurrency import get_device

        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device=get_device())
    return _reranker


@dataclass
class Candidate:
    text: str
    origin: str  # "request" (this request's external/uploaded content) or "main_db" (already-approved data)
    chunk_id: str
    product_id: str | None = None  # set when origin == "main_db", for Validate step conflict lookups


def _fetch_request_candidates(db: Session, temp_request_id, source_type: str) -> list[Candidate]:
    """Source 2 of 3: this request's own external/uploaded content for the
    given source_type — the chunks created in Phase 3/4/5."""
    rows = db.execute(
        select(TempChunk.id, TempChunk.text)
        .join(TempDocument, TempChunk.temp_document_id == TempDocument.id)
        .where(TempDocument.temp_request_id == temp_request_id, TempDocument.source_type == source_type)
    ).all()
    return [Candidate(text=r.text, origin="request", chunk_id=str(r.id)) for r in rows]


def _fetch_main_db_candidates(db: Session, limit: int = 500) -> list[Candidate]:
    """Source 3 of 3: already-approved product knowledge in the Main DB —
    used to cross-reference and catch conflicts with newly retrieved data."""
    rows = db.execute(
        select(Chunk.id, Chunk.text, Document.product_id).join(Document, Chunk.document_id == Document.id).limit(limit)
    ).all()
    return [Candidate(text=r.text, origin="main_db", chunk_id=str(r.id), product_id=str(r.product_id) if r.product_id else None) for r in rows]


def _rrf_fuse(vector_ranked_ids: list[str], bm25_ranked_ids: list[str]) -> list[str]:
    """Reciprocal Rank Fusion: combines two independently-ranked lists without
    needing their raw scores to be on the same scale (cosine distance and
    BM25 scores aren't comparable directly)."""
    scores: dict[str, float] = {}
    for rank, cid in enumerate(vector_ranked_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, cid in enumerate(bm25_ranked_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)


def hybrid_rag_retrieve(db: Session, query_text: str, source_type: str, temp_request_id, top_k: int = 5) -> list[dict]:
    """Source 1 of 3 (input embedding) drives retrieval against sources 2 and 3
    (this request's content + Main DB). Pipeline: vector search + BM25 search
    over the combined candidate pool -> RRF fusion -> cross-encoder rerank on
    the fused shortlist only -> top_k final results.

    Returns [{"text", "origin", "chunk_id", "product_id", "score"}], sorted
    best-first. `origin` distinguishes "request" (freshly retrieved) from
    "main_db" (already-approved) so the Validate step can catch conflicts
    rather than silently overwriting one with the other.
    """
    candidates = _fetch_request_candidates(db, temp_request_id, source_type) + _fetch_main_db_candidates(db)
    if not candidates:
        return []

    by_id = {c.chunk_id: c for c in candidates}

    # --- Vector ranking ---
    query_vector = embed_texts([query_text])[0]
    request_chunk_ids = [c.chunk_id for c in candidates if c.origin == "request"]
    main_chunk_ids = [c.chunk_id for c in candidates if c.origin == "main_db"]

    vector_ranked_ids: list[str] = []
    if request_chunk_ids:
        rows = db.execute(
            select(TempEmbedding.temp_chunk_id)
            .where(TempEmbedding.temp_chunk_id.in_(request_chunk_ids))
            .order_by(TempEmbedding.vector.cosine_distance(query_vector).asc())
            .limit(FUSION_POOL_SIZE)
        ).all()
        vector_ranked_ids += [str(r.temp_chunk_id) for r in rows]
    if main_chunk_ids:
        rows = db.execute(
            select(Embedding.chunk_id)
            .where(Embedding.chunk_id.in_(main_chunk_ids))
            .order_by(Embedding.vector.cosine_distance(query_vector).asc())
            .limit(FUSION_POOL_SIZE)
        ).all()
        vector_ranked_ids += [str(r.chunk_id) for r in rows]

    # --- BM25 keyword ranking (over the same combined pool) ---
    tokenized_corpus = [c.text.lower().split() for c in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(query_text.lower().split())
    bm25_ranked_ids = [
        cid for cid, _ in sorted(zip(by_id.keys(), bm25_scores), key=lambda x: x[1], reverse=True)[:FUSION_POOL_SIZE]
    ]

    # --- RRF fusion ---
    fused_ids = _rrf_fuse(vector_ranked_ids, bm25_ranked_ids)[:RERANK_SHORTLIST_SIZE]
    if not fused_ids:
        return []

    # --- Cross-encoder rerank on the shortlist only (not the full pool) ---
    reranker = _get_reranker()
    pairs = [(query_text, by_id[cid].text) for cid in fused_ids]
    rerank_scores = reranker.predict(pairs)

    ranked = sorted(zip(fused_ids, rerank_scores), key=lambda x: x[1], reverse=True)[:top_k]

    return [
        {
            "text": by_id[cid].text,
            "origin": by_id[cid].origin,
            "chunk_id": cid,
            "product_id": by_id[cid].product_id,
            "score": float(score),
        }
        for cid, score in ranked
    ]

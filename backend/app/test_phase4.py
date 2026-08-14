"""
Run after the backend is up (first run downloads the ~90MB embedding model):
    docker compose exec backend python -m app.test_phase4

Exits non-zero if any check fails.
"""
import sys

from sqlalchemy import select, text

from app.chunking.chunker import chunk_text
from app.db import SessionLocal
from app.embeddings.embedder import embed_texts
from app.models import EMBEDDING_DIM, TempChunk, TempDocument, TempEmbedding, TempRequest
from app.services.chunk_embed_service import process_request_chunks_and_embeddings

results = []


def check(description, passed):
    results.append((description, passed))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {description}")


def main():
    # -----------------------------------------------------------------
    # 1) Known text in -> N chunks out, matches expected count
    # -----------------------------------------------------------------
    words = [f"word{i}" for i in range(1000)]
    sample_text = " ".join(words)
    chunks = chunk_text(sample_text, chunk_size_words=100, overlap_words=20)

    # Hand-computed expected count for 1000 words, size=100, overlap=20, step=80:
    # starts land at 0,80,160,...,960 -> 13 chunks total.
    check(f"chunker: 1000 words/size100/overlap20 -> 13 chunks (got {len(chunks)})", len(chunks) == 13)
    check("chunker: first chunk starts at word0", chunks[0].startswith("word0 "))
    check("chunker: second chunk starts at word80 (overlap applied)", chunks[1].startswith("word80 "))
    check("chunker: last chunk ends at word999", chunks[-1].endswith("word999"))

    # -----------------------------------------------------------------
    # 2) Each chunk has an embedding row, dimension matches schema
    # -----------------------------------------------------------------
    db = SessionLocal()
    temp_request = None
    try:
        temp_request = TempRequest(user_text="phase 4 test request", sources_selected=[])
        db.add(temp_request)
        db.flush()

        doc_a = TempDocument(
            temp_request_id=temp_request.id,
            source_type="user_upload",
            extraction_status="success",
            extracted_text=(
                "The keyboard features hot-swappable mechanical switches, per-key RGB "
                "backlighting, and a detachable USB-C cable. Battery life reaches 40 hours "
                "with backlighting disabled, or 10 hours with RGB fully active."
            ),
        )
        doc_b_near_dup = TempDocument(
            temp_request_id=temp_request.id,
            source_type="user_upload",
            extraction_status="success",
            extracted_text=(
                "This mechanical keyboard has hot-swappable switches, RGB backlighting per "
                "key, and a detachable USB-C cable. Battery life is 40 hours with the "
                "backlight off, or about 10 hours with RGB on."
            ),
        )
        doc_c_unrelated = TempDocument(
            temp_request_id=temp_request.id,
            source_type="user_upload",
            extraction_status="success",
            extracted_text=(
                "This stainless steel water bottle keeps drinks cold for 24 hours and hot "
                "for 12 hours. It has a leak-proof lid and holds 750ml of liquid."
            ),
        )
        doc_skipped = TempDocument(
            temp_request_id=temp_request.id,
            source_type="user_upload",
            extraction_status="failed",
            extracted_text=None,
        )
        db.add_all([doc_a, doc_b_near_dup, doc_c_unrelated, doc_skipped])
        db.flush()

        summary = process_request_chunks_and_embeddings(db, temp_request)

        check("chunk_and_embed: skips docs with extraction_status != success", summary["documents_processed"] == 3)
        check("chunk_and_embed: chunks_created == embeddings_created", summary["chunks_created"] == summary["embeddings_created"])
        check("chunk_and_embed: at least one chunk created", summary["chunks_created"] > 0)

        all_chunks = (
            db.execute(select(TempChunk).where(TempChunk.temp_document_id.in_([doc_a.id, doc_b_near_dup.id, doc_c_unrelated.id])))
            .scalars()
            .all()
        )
        all_have_embeddings = all(c.embedding is not None for c in all_chunks)
        check("every chunk has a corresponding embedding row", all_have_embeddings)

        dims_ok = all(len(c.embedding.vector) == EMBEDDING_DIM for c in all_chunks if c.embedding)
        check(f"every embedding vector has dimension {EMBEDDING_DIM}", dims_ok)

        # -----------------------------------------------------------------
        # 3) Similarity search: near-duplicate chunks should be each other's top match
        # -----------------------------------------------------------------
        chunk_a = next(c for c in all_chunks if c.temp_document_id == doc_a.id)
        chunk_b = next(c for c in all_chunks if c.temp_document_id == doc_b_near_dup.id)

        nearest_to_a = db.execute(
            select(TempEmbedding.temp_chunk_id, TempEmbedding.vector.cosine_distance(chunk_a.embedding.vector).label("distance"))
            .where(TempEmbedding.temp_chunk_id.in_([chunk_b.id, chunk_c.id]))  # scope to THIS test's own chunks only
            .order_by(text("distance ASC"))
            .limit(1)
        ).first()

        check(
            "near-duplicate chunk ranks as nearest neighbor (not the unrelated chunk)",
            nearest_to_a is not None and nearest_to_a.temp_chunk_id == chunk_b.id,
        )

        # -----------------------------------------------------------------
        # 4) Round trip: fresh query embedding vs stored -> sane cosine similarity
        # -----------------------------------------------------------------
        query_vector = embed_texts(["hot-swappable mechanical keyboard with RGB backlighting"])[0]

        chunk_c = next(c for c in all_chunks if c.temp_document_id == doc_c_unrelated.id)

        dist_to_relevant = db.execute(
            select(TempEmbedding.vector.cosine_distance(query_vector)).where(TempEmbedding.temp_chunk_id == chunk_a.id)
        ).scalar()
        dist_to_control = db.execute(
            select(TempEmbedding.vector.cosine_distance(query_vector)).where(TempEmbedding.temp_chunk_id == chunk_c.id)
        ).scalar()

        similarity_to_relevant = 1 - dist_to_relevant
        similarity_to_control = 1 - dist_to_control

        check(
            f"query embedding: similarity to relevant chunk ({similarity_to_relevant:.2f}) > 0.5",
            similarity_to_relevant > 0.5,
        )
        check(
            f"query embedding: similarity to relevant ({similarity_to_relevant:.2f}) > control ({similarity_to_control:.2f})",
            similarity_to_relevant > similarity_to_control,
        )

    finally:
        # Clean up this test's own rows so repeated runs don't accumulate
        # leftover data that could pollute future similarity-search tests.
        try:
            db.rollback()
            if temp_request is not None:
                db.query(TempRequest).filter(TempRequest.id == temp_request.id).delete()
                db.commit()
        except Exception:
            db.rollback()
        db.close()

    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()

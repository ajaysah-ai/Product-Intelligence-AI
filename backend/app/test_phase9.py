"""
Run after the backend is up:
    docker compose exec backend python -m app.test_phase9

Exits non-zero if any check fails.
"""
import sys
import uuid

from sqlalchemy import select

from app.approval.service import approve_request
from app.db import SessionLocal
from app.models import Chunk, Document, Embedding, Product, ProductAttribute, TempDocument, TempRequest
from app.orchestration.hybrid_rag import hybrid_rag_retrieve
from app.orchestration.service import orchestrate_request
from app.services.chunk_embed_service import process_request_chunks_and_embeddings

results = []


def check(description, passed):
    results.append((description, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] {description}")


def main():
    db = SessionLocal()
    request_id = None
    product_id_to_clean = None
    product_id_to_clean_2 = None

    try:
        # -----------------------------------------------------------------
        # Setup: a request with content, run through orchestrate to get a draft
        # -----------------------------------------------------------------
        temp_request = TempRequest(
            user_text="Stainless Steel Water Bottle 750ml",
            sources_selected=["website"],
            mfg_part_num="WB-750",
            part_desc="Stainless Steel Water Bottle 750ml",
            e1_brand="HydroBrand",
            unilog_brand="HydroBrand",
            dib_brand="HydroBrand",
            part_manuf="Test Distributor",
        )
        db.add(temp_request)
        db.commit()
        request_id = str(temp_request.id)

        doc = TempDocument(
            temp_request_id=temp_request.id,
            source_type="website",
            extraction_status="success",
            extracted_text=(
                "Stainless Steel Water Bottle 750ml keeps drinks cold for 24 hours. "
                "Leak-proof lid. Rated capacity 750ml. Weighs 350g."
            ),
        )
        db.add(doc)
        db.commit()
        process_request_chunks_and_embeddings(db, temp_request)

        orch_result = orchestrate_request(db, request_id, urls={})
        check("setup: orchestrate produced a draft", "detected_product_id" in orch_result)

        # -----------------------------------------------------------------
        # 1) Approve -> row appears in products/documents/chunks/embeddings/product_attributes
        # -----------------------------------------------------------------
        approve_result = approve_request(db, request_id, overrides={})
        check("approve -> status 'approved'", approve_result.get("status") == "approved")
        product_id = approve_result.get("product_id")
        product_id_to_clean = product_id

        if product_id:
            product = db.get(Product, product_id)
            check("Product row exists in Main DB", product is not None)

            docs = db.execute(select(Document).where(Document.product_id == product_id)).scalars().all()
            check("Document row(s) copied to Main DB", len(docs) >= 1)

            if docs:
                chunks = db.execute(select(Chunk).where(Chunk.document_id == docs[0].id)).scalars().all()
                check("Chunk row(s) copied to Main DB", len(chunks) >= 1)

                if chunks:
                    embeddings = db.execute(select(Embedding).where(Embedding.chunk_id == chunks[0].id)).scalars().all()
                    check("Embedding row copied to Main DB", len(embeddings) == 1)

            attrs = db.execute(select(ProductAttribute).where(ProductAttribute.product_id == product_id)).scalars().all()
            check("ProductAttribute row(s) copied to Main DB", len(attrs) >= 1)

        # -----------------------------------------------------------------
        # 2) Temp rows cleared after successful approval
        # -----------------------------------------------------------------
        remaining_temp_request = db.get(TempRequest, request_id)
        check("temp_request deleted after successful approval", remaining_temp_request is None)

        # -----------------------------------------------------------------
        # 3) Approve fails mid-transaction -> full rollback, nothing partially written
        # -----------------------------------------------------------------
        temp_request_2 = TempRequest(
            user_text="Cordless Drill 20V",
            sources_selected=["website"],
            mfg_part_num="CD-20V",
            part_desc="Cordless Drill 20V",
            e1_brand="ToolBrand",
            unilog_brand="ToolBrand",
            dib_brand="ToolBrand",
            part_manuf="Test Distributor",
        )
        db.add(temp_request_2)
        db.commit()
        request_id_2 = str(temp_request_2.id)

        doc2 = TempDocument(
            temp_request_id=temp_request_2.id,
            source_type="website",
            extraction_status="success",
            extracted_text="Cordless Drill 20V with 2 batteries. Rated power 400W.",
        )
        db.add(doc2)
        db.commit()
        process_request_chunks_and_embeddings(db, temp_request_2)
        orchestrate_request(db, request_id_2, urls={})

        products_before = db.execute(select(Product).where(Product.mfg_part_num == "CD-20V")).scalars().all()

        # Deliberately invalid: confidence must be an Integer column — a
        # non-numeric string forces a real DB-level failure mid-transaction.
        bad_overrides = {"specs": [{"key": "power", "value": "400W", "unit": "W", "confidence": "not-a-number"}]}
        failed_result = approve_request(db, request_id_2, overrides=bad_overrides)
        check("approve with invalid data reports an error (not a silent partial success)", "error" in failed_result)

        products_after = db.execute(select(Product).where(Product.mfg_part_num == "CD-20V")).scalars().all()
        check("failed approve created NO Product row (full rollback)", len(products_after) == len(products_before))

        still_there = db.get(TempRequest, request_id_2)
        check("failed approve left temp data intact for retry", still_there is not None)

        # Retry with valid data should now succeed, proving the DB session recovered cleanly
        retry_result = approve_request(db, request_id_2, overrides={})
        check("retry with valid data succeeds after a prior failed attempt", retry_result.get("status") == "approved")
        product_id_to_clean_2 = retry_result.get("product_id")

        # -----------------------------------------------------------------
        # 4) Main DB retrieval: a second, unrelated request can find the approved product
        # -----------------------------------------------------------------
        unrelated_request_id = str(uuid.uuid4())  # doesn't need to exist — Hybrid RAG's request-side pool is just empty
        retrieved = hybrid_rag_retrieve(
            db, "stainless steel water bottle 750ml cold drinks", "website", unrelated_request_id, top_k=5
        )
        found_in_main_db = any(r["origin"] == "main_db" and r["product_id"] == product_id for r in retrieved)
        check("a second unrelated request can retrieve the approved product via Hybrid RAG", found_in_main_db)

    finally:
        try:
            db.rollback()
            if product_id_to_clean:
                db.query(Product).filter(Product.id == product_id_to_clean).delete()
            if product_id_to_clean_2:
                db.query(Product).filter(Product.id == product_id_to_clean_2).delete()
            db.commit()
        except Exception:
            db.rollback()
        db.close()

    total, passed = len(results), sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()

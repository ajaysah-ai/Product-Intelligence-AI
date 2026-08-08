"""
Run after init_db:
    docker compose exec backend python -m app.test_phase1

Exits non-zero if any check fails, so it's CI/script-friendly.
"""
import sys
import uuid

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import (
    EMBEDDING_DIM,
    Chunk,
    Document,
    Embedding,
    Product,
    ProductAttribute,
    TempChunk,
    TempDetectedProduct,
    TempDocument,
    TempEmbedding,
    TempProductAttribute,
    TempRequest,
)

results = []  # (description, bool)


def check(description, passed):
    results.append((description, passed))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {description}")


def main():
    db = SessionLocal()
    temp_req = None
    product = None

    # -----------------------------------------------------------------
    # 1) Insert a dummy row into each of the 11 tables, read it back
    # -----------------------------------------------------------------
    try:
        temp_req = TempRequest(user_text="test product intelligence request", sources_selected=["website"])
        db.add(temp_req)
        db.flush()

        temp_doc = TempDocument(temp_request_id=temp_req.id, source_type="website", external_url="https://example.com")
        db.add(temp_doc)
        db.flush()

        temp_chunk = TempChunk(temp_document_id=temp_doc.id, chunk_index=0, text="sample chunk text")
        db.add(temp_chunk)
        db.flush()

        rng = np.random.default_rng(42)
        base_vector = rng.random(EMBEDDING_DIM).tolist()

        temp_emb = TempEmbedding(temp_chunk_id=temp_chunk.id, vector=base_vector, model_name="test-model")
        db.add(temp_emb)
        db.flush()

        temp_detected = TempDetectedProduct(temp_request_id=temp_req.id, title="Test Product Draft")
        db.add(temp_detected)
        db.flush()

        temp_attr = TempProductAttribute(
            temp_detected_product_id=temp_detected.id,
            attribute_type="spec",
            attribute_key="power",
            attribute_value="750",
            unit="W",
            confidence=99,
        )
        db.add(temp_attr)
        db.flush()

        product = Product(title="Test Product")
        db.add(product)
        db.flush()

        doc = Document(product_id=product.id, source_type="user_upload", file_path="/media/test.pdf")
        db.add(doc)
        db.flush()

        chunk = Chunk(document_id=doc.id, chunk_index=0, text="sample chunk text")
        db.add(chunk)
        db.flush()

        near_duplicate_vector = (np.array(base_vector) + rng.normal(0, 0.01, EMBEDDING_DIM)).tolist()
        emb = Embedding(chunk_id=chunk.id, vector=near_duplicate_vector, model_name="test-model")
        db.add(emb)
        db.flush()

        attr = ProductAttribute(
            product_id=product.id,
            attribute_type="spec",
            attribute_key="power",
            attribute_value="750",
            unit="W",
            confidence=99,
        )
        db.add(attr)
        db.commit()

        # Read back — confirm all 11 rows exist
        checks = {
            "temp_requests": db.get(TempRequest, temp_req.id),
            "temp_documents": db.get(TempDocument, temp_doc.id),
            "temp_chunks": db.get(TempChunk, temp_chunk.id),
            "temp_embeddings": db.get(TempEmbedding, temp_emb.id),
            "temp_detected_products": db.get(TempDetectedProduct, temp_detected.id),
            "temp_product_attributes": db.get(TempProductAttribute, temp_attr.id),
            "products": db.get(Product, product.id),
            "documents": db.get(Document, doc.id),
            "chunks": db.get(Chunk, chunk.id),
            "embeddings": db.get(Embedding, emb.id),
            "product_attributes": db.get(ProductAttribute, attr.id),
        }
        for table_name, row in checks.items():
            check(f"insert + read back row in `{table_name}`", row is not None)

    except Exception as e:
        db.rollback()
        check(f"insert + read back across all 11 tables (exception: {e})", False)

    # -----------------------------------------------------------------
    # 2) Vector similarity: near-duplicate should rank above a random control
    # -----------------------------------------------------------------
    try:
        control_vector = rng.random(EMBEDDING_DIM).tolist()  # unrelated random vector, control
        control_chunk = Chunk(document_id=doc.id, chunk_index=1, text="unrelated control chunk")
        db.add(control_chunk)
        db.flush()
        control_emb = Embedding(chunk_id=control_chunk.id, vector=control_vector, model_name="test-model")
        db.add(control_emb)
        db.commit()

        query_vector = base_vector  # same as the "near duplicate" embedding's origin
        nearest = db.execute(
            select(Embedding.id, Embedding.vector.cosine_distance(query_vector).label("distance"))
            .where(Embedding.id.in_([emb.id, control_emb.id]))  # scope to THIS test's own rows only
            .order_by(text("distance ASC"))
            .limit(1)
        ).first()

        check(
            "cosine similarity search ranks near-duplicate above random control",
            nearest is not None and nearest.id == emb.id,
        )
    except Exception as e:
        db.rollback()
        check(f"vector similarity search (exception: {e})", False)

    # -----------------------------------------------------------------
    # 3) Foreign key rejection: orphan insert must fail
    # -----------------------------------------------------------------
    try:
        bad_chunk = Chunk(document_id=uuid.uuid4(), chunk_index=99, text="orphan chunk, should be rejected")
        db.add(bad_chunk)
        db.commit()
        check("FK constraint rejects orphan chunk (no matching document_id)", False)
    except IntegrityError:
        db.rollback()
        check("FK constraint rejects orphan chunk (no matching document_id)", True)
    except Exception as e:
        db.rollback()
        check(f"FK constraint test (unexpected exception: {e})", False)

    # Clean up this test's own rows so repeated runs don't accumulate leftover
    # data that could pollute later similarity-search checks (in this or other
    # phase test scripts). Cascades via ondelete=CASCADE clear the children.
    try:
        db.rollback()
        if temp_req is not None:
            db.query(TempRequest).filter(TempRequest.id == temp_req.id).delete()
        if product is not None:
            db.query(Product).filter(Product.id == product.id).delete()
        db.commit()
    except Exception:
        db.rollback()

    db.close()

    # -----------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()

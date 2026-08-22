from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Chunk,
    Document,
    Embedding,
    Product,
    ProductAttribute,
    TempChunk,
    TempDetectedProduct,
    TempDocument,
    TempProductAttribute,
    TempRequest,
)


def approve_request(db: Session, request_id: str, overrides: dict | None = None) -> dict:
    """Transfers a request's approved draft into the Main DB. Copies the
    underlying documents/chunks/embeddings too (not just the flattened
    attributes) so they remain available as provenance and as future Hybrid
    RAG cross-reference candidates. Everything happens in ONE transaction —
    on any failure, nothing is partially written and temp data is left
    untouched for retry. Temp rows are only deleted after a fully successful
    commit.

    overrides (optional, from a frontend edit before approving):
        {"title", "manufacturer_name", "delivery_fields" (merged over stored),
         "specs" (full replacement), "features" (full replacement)}
    """
    overrides = overrides or {}

    temp_request = db.get(TempRequest, request_id)
    if temp_request is None:
        return {"error": "request_id not found"}

    detected = (
        db.execute(
            select(TempDetectedProduct)
            .where(TempDetectedProduct.temp_request_id == temp_request.id)
            .order_by(TempDetectedProduct.created_at.desc())
        )
        .scalars()
        .first()
    )
    if detected is None:
        return {"error": "No detected product for this request — run /orchestrate first"}

    try:
        product = Product(
            title=overrides.get("title") or detected.title or "Untitled Product",
            source_request_id=temp_request.id,
            mfg_part_num=detected.mfg_part_num,
            part_desc=detected.part_desc,
            e1_brand=detected.e1_brand,
            unilog_brand=detected.unilog_brand,
            dib_brand=detected.dib_brand,
            part_manuf=detected.part_manuf,
            manufacturer_name=overrides.get("manufacturer_name") or detected.manufacturer_name,
            delivery_fields={**(detected.delivery_fields or {}), **(overrides.get("delivery_fields") or {})},
            agent_provenance=detected.agent_provenance,
        )
        db.add(product)
        db.flush()

        # --- Copy documents/chunks/embeddings as provenance + future retrieval candidates ---
        temp_docs = db.execute(select(TempDocument).where(TempDocument.temp_request_id == temp_request.id)).scalars().all()
        for temp_doc in temp_docs:
            new_doc = Document(
                product_id=product.id,
                source_type=temp_doc.source_type,
                file_path=temp_doc.file_path,
                external_url=temp_doc.external_url,
                mime_type=temp_doc.mime_type,
                extracted_text=temp_doc.extracted_text,
                extraction_status=temp_doc.extraction_status,
                extraction_error=temp_doc.extraction_error,
            )
            db.add(new_doc)
            db.flush()

            temp_chunks = (
                db.execute(select(TempChunk).where(TempChunk.temp_document_id == temp_doc.id)).scalars().all()
            )
            for temp_chunk in temp_chunks:
                new_chunk = Chunk(document_id=new_doc.id, chunk_index=temp_chunk.chunk_index, text=temp_chunk.text)
                db.add(new_chunk)
                db.flush()

                if temp_chunk.embedding is not None:
                    db.add(
                        Embedding(
                            chunk_id=new_chunk.id,
                            vector=temp_chunk.embedding.vector,
                            model_name=temp_chunk.embedding.model_name,
                        )
                    )

        # --- Attributes: use frontend overrides if given, else copy the stored draft ---
        if "specs" in overrides or "features" in overrides:
            for spec in overrides.get("specs", []):
                db.add(
                    ProductAttribute(
                        product_id=product.id,
                        attribute_type="spec",
                        attribute_key=spec.get("key"),
                        attribute_value=spec.get("value"),
                        unit=spec.get("unit") or spec.get("uom"),
                        confidence=spec.get("confidence"),
                    )
                )
            for feature in overrides.get("features", []):
                value = feature.get("value") if isinstance(feature, dict) else feature
                db.add(ProductAttribute(product_id=product.id, attribute_type="feature", attribute_value=value))
        else:
            temp_attrs = (
                db.execute(
                    select(TempProductAttribute).where(TempProductAttribute.temp_detected_product_id == detected.id)
                )
                .scalars()
                .all()
            )
            for attr in temp_attrs:
                db.add(
                    ProductAttribute(
                        product_id=product.id,
                        attribute_type=attr.attribute_type,
                        attribute_key=attr.attribute_key,
                        attribute_value=attr.attribute_value,
                        unit=attr.unit,
                        confidence=attr.confidence,
                        extra=attr.extra,
                    )
                )

        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"Approval failed, rolled back: {e}", "approved": False}

    product_id = str(product.id)

    # Cleanup only runs after a fully successful commit — a failed approval
    # above returns before this point, leaving temp data intact for retry.
    try:
        db.query(TempRequest).filter(TempRequest.id == temp_request.id).delete()
        db.commit()
    except Exception:
        db.rollback()  # product is already safely committed; cleanup failure isn't fatal

    return {"request_id": request_id, "product_id": product_id, "status": "approved"}

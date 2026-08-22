"""
Run after the backend is up:
    docker compose exec backend python -m app.test_concurrency

Exits non-zero if any check fails.
"""
import os
import sys

from fastapi.testclient import TestClient

from app.concurrency import get_device, get_worker_count
from app.db import SessionLocal
from app.main import app
from app.models import Product, TempDocument, TempRequest
from app.services.chunk_embed_service import process_request_chunks_and_embeddings

client = TestClient(app)
results = []


def check(description, passed):
    results.append((description, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] {description}")


def main():
    # -----------------------------------------------------------------
    # Worker count follows the cores-2 rule
    # -----------------------------------------------------------------
    cpu = os.cpu_count() or 4
    expected = max(1, cpu - 2)
    actual = get_worker_count()
    check(f"get_worker_count() == cpu_count-2 (cpu={cpu}, expected={expected}, got={actual})", actual == expected)

    # -----------------------------------------------------------------
    # Device detection doesn't error, returns a valid value
    # -----------------------------------------------------------------
    device = get_device()
    check(f"get_device() returns a valid value (got '{device}')", device in ("cpu", "cuda"))

    # -----------------------------------------------------------------
    # Batch orchestration: multiple requests processed concurrently
    # -----------------------------------------------------------------
    db = SessionLocal()
    request_ids = []
    product_ids_to_clean = []

    try:
        products_data = [
            ("Bluetooth Speaker X100", "waterproof rated IPX7, 12 hour battery, 20W output"),
            ("USB-C Hub 7-in-1", "supports 4K HDMI, 100W passthrough, aluminum body"),
            ("Ergonomic Office Chair", "adjustable lumbar support, mesh back, 150kg capacity"),
        ]
        for title, desc_text in products_data:
            temp_request = TempRequest(user_text=f"{title} {desc_text}", sources_selected=["website"])
            db.add(temp_request)
            db.commit()
            request_ids.append(str(temp_request.id))

            doc = TempDocument(
                temp_request_id=temp_request.id,
                source_type="website",
                extraction_status="success",
                extracted_text=f"{title}. {desc_text}.",
            )
            db.add(doc)
            db.commit()
            process_request_chunks_and_embeddings(db, temp_request)

        r = client.post("/orchestrate-batch", json={"request_ids": request_ids})
        check("orchestrate-batch -> 200", r.status_code == 200)
        body = r.json() if r.status_code == 200 else {}
        check(f"orchestrate-batch processed all {len(request_ids)} requests", body.get("processed") == len(request_ids))
        check(
            f"orchestrate-batch used bounded worker count (<= {get_worker_count()})",
            body.get("workers_used", 999) <= get_worker_count(),
        )

        all_succeeded = all("detected_product_id" in r for r in body.get("results", []))
        check("all batch requests produced a draft (no errors)", all_succeeded)

        # -----------------------------------------------------------------
        # Bulk export: approve one, confirm it shows up in the multi-row export
        # -----------------------------------------------------------------
        from app.approval.service import approve_request

        approve_result = approve_request(db, request_ids[0], overrides={})
        check("approve (from batch draft) -> status 'approved'", approve_result.get("status") == "approved")
        if approve_result.get("product_id"):
            product_ids_to_clean.append(approve_result["product_id"])

        r2 = client.get("/export-all")
        check("export-all -> 200", r2.status_code == 200)
        check("export-all content-type is text/csv", r2.headers.get("content-type", "").startswith("text/csv"))

        import csv
        import io

        reader = csv.DictReader(io.StringIO(r2.text))
        from app.delivery.schema import DELIVERY_COLUMNS

        check("export-all header matches the 252-column format", reader.fieldnames == DELIVERY_COLUMNS)

        rows = list(reader)
        check("export-all includes at least the just-approved product", len(rows) >= 1)
        titles_in_export = [row.get("Product Name", "") for row in rows]
        check(
            "export-all row contains real title text (not blank)",
            any(t.strip() for t in titles_in_export),
        )

    finally:
        try:
            db.rollback()
            for rid in request_ids:
                db.query(TempRequest).filter(TempRequest.id == rid).delete()
            for pid in product_ids_to_clean:
                db.query(Product).filter(Product.id == pid).delete()
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

"""
Run after the backend is up:
    docker compose exec backend python -m app.test_phase7

Pre-seeds content directly (like Phase 6's test) rather than relying on live
web search or MCP fetch, so this stays deterministic and offline-testable.
The DuckDuckGo HTML parser itself is tested separately against a static
fixture, so its correctness is still verified without needing internet.

Exits non-zero if any check fails.
"""
import csv
import io
import sys

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.delivery.schema import DELIVERY_COLUMNS
from app.main import app
from app.models import TempDocument, TempRequest
from app.orchestration.web_search import parse_duckduckgo_html
from app.services.chunk_embed_service import process_request_chunks_and_embeddings

client = TestClient(app)
results = []


def check(description, passed):
    results.append((description, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] {description}")


DUCKDUCKGO_FIXTURE_HTML = """
<div class="result">
  <a class="result__a" href="https://example.com/product">Example Product Page</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/spec.pdf">Spec Sheet PDF</a>
</div>
"""


def main():
    request_id = None

    # -----------------------------------------------------------------
    # Web search HTML parsing works offline (no live internet needed)
    # -----------------------------------------------------------------
    parsed = parse_duckduckgo_html(DUCKDUCKGO_FIXTURE_HTML, max_results=3)
    check(
        "DuckDuckGo result parser extracts links from a static fixture",
        len(parsed) == 2 and parsed[0]["url"] == "https://example.com/product",
    )

    try:
        # -----------------------------------------------------------------
        # Bulk import: one row, matching the hackathon's exact input shape
        # -----------------------------------------------------------------
        csv_content = (
            "Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand,Part_Manuf\n"
            "XJ-500,Wireless Mechanical Keyboard,TestBrand,TestBrand,TestBrand,Test Distributor\n"
        )
        r = client.post("/import-dataset", files={"file": ("input.csv", io.BytesIO(csv_content.encode()), "text/csv")})
        check("import-dataset -> 200", r.status_code == 200)
        body = r.json() if r.status_code == 200 else {}
        check("import-dataset imported exactly 1 row", body.get("imported_count") == 1)
        request_id = body.get("request_ids", [None])[0]
        check("import produced a request_id", bool(request_id))

        if request_id:
            # -----------------------------------------------------------------
            # Pre-seed content (bypasses live web search/fetch for determinism)
            # -----------------------------------------------------------------
            db = SessionLocal()
            try:
                temp_request = db.get(TempRequest, request_id)
                temp_request.sources_selected = ["website"]  # restrict to 1 source, keep the test fast
                doc = TempDocument(
                    temp_request_id=temp_request.id,
                    source_type="website",
                    extraction_status="success",
                    extracted_text=(
                        "Wireless Mechanical Keyboard XJ-500 by TestBrand. Rated power 750W. "
                        "Hot-swappable switches. RGB backlighting. Weighs 900g."
                    ),
                )
                db.add(doc)
                db.commit()
                process_request_chunks_and_embeddings(db, temp_request)
            finally:
                db.close()

            # -----------------------------------------------------------------
            # Orchestrate
            # -----------------------------------------------------------------
            r2 = client.post(f"/orchestrate/{request_id}", json={})
            check("orchestrate -> 200", r2.status_code == 200)
            orch_body = r2.json() if r2.status_code == 200 else {}
            check("orchestrate produced a detected_product_id", "detected_product_id" in orch_body)

            # -----------------------------------------------------------------
            # Export and validate the exact delivery format
            # -----------------------------------------------------------------
            r3 = client.get(f"/export/{request_id}")
            check("export -> 200", r3.status_code == 200)
            check("export content-type is text/csv", r3.headers.get("content-type", "").startswith("text/csv"))

            reader = csv.DictReader(io.StringIO(r3.text))
            exported_header = reader.fieldnames
            check("exported CSV header matches the 252-column delivery format exactly", exported_header == DELIVERY_COLUMNS)

            rows = list(reader)
            check("exported CSV has exactly 1 data row", len(rows) == 1)

            if rows:
                row = rows[0]
                check("passthrough Mfg_Part_Num matches input", row["Mfg_Part_Num"] == "XJ-500")
                check("passthrough Part_Desc matches input", row["Part_Desc"] == "Wireless Mechanical Keyboard")
                check("Product Name populated from orchestration", bool(row["Product Name"].strip()))
                has_attribute = any(row[f"ATTRIBUTE_LABEL {i}"].strip() for i in range(1, 51))
                check("at least one ATTRIBUTE_LABEL slot populated from retrieved content", has_attribute)

    finally:
        if request_id:
            db = SessionLocal()
            try:
                db.rollback()
                db.query(TempRequest).filter(TempRequest.id == request_id).delete()
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()

    total, passed = len(results), sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()

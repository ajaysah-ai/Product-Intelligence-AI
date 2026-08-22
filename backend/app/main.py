import csv
import io
import json
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, Form, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approval.service import approve_request
from app.config import MEDIA_DIR
from app.db import check_db_connection
from app.delivery.export import build_delivery_row
from app.delivery.schema import DELIVERY_COLUMNS
from app.deps import get_db
from app.extraction.batch import extract_batch
from app.mcp_client.client import call_source_agent
from app.models import Product, ProductAttribute, TempDetectedProduct, TempDocument, TempProductAttribute, TempRequest
from app.orchestration.service import orchestrate_batch, orchestrate_request
from app.services.chunk_embed_service import process_request_chunks_and_embeddings
from app.validation import validate_single_file, validate_text_and_files

app = FastAPI(title="Product Intelligence AI - Backend")

# Phase 0: wide open CORS for local dev. Tighten before demo/deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    ok = check_db_connection()
    return {"status": "ok" if ok else "unreachable", "db_connected": ok}


@app.post("/submit")
async def submit(
    text: Optional[str] = Form(None),
    sources_selected: Optional[str] = Form(None),  # JSON-encoded list, e.g. '["website","catalog"]'
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    # Filter out the phantom empty UploadFile FastAPI sends when the files field is untouched
    files = [f for f in files if f.filename]

    validate_text_and_files(text, files)

    parsed_sources: list[str] = []
    if sources_selected:
        try:
            parsed_sources = json.loads(sources_selected)
        except json.JSONDecodeError:
            parsed_sources = []

    # Read + validate every file BEFORE writing anything to disk or DB,
    # so a bad file in a multi-file batch rejects the whole request cleanly.
    file_payloads = []
    for f in files:
        content = await f.read()
        validate_single_file(f.filename, content)
        file_payloads.append((f.filename, content))

    temp_request = TempRequest(
        user_text=text.strip() if text else None,
        sources_selected=parsed_sources,
        status="pending",
    )
    db.add(temp_request)
    db.flush()  # get temp_request.id without committing yet

    request_dir = MEDIA_DIR / str(temp_request.id)
    request_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for filename, content in file_payloads:
        dest = request_dir / filename
        dest.write_bytes(content)

        doc = TempDocument(
            temp_request_id=temp_request.id,
            source_type="user_upload",
            file_path=str(dest),
            mime_type=None,
        )
        db.add(doc)
        saved_files.append(filename)

    db.commit()

    return {
        "request_id": str(temp_request.id),
        "text_saved": bool(text and text.strip()),
        "accepted_files": saved_files,
        "sources_selected": parsed_sources,
    }


@app.post("/extract/{request_id}")
def extract(request_id: str, db: Session = Depends(get_db)):
    """Runs the extraction pipeline over every uploaded file for a request,
    concurrently, and stores each result back onto its temp_documents row."""
    temp_request = db.get(TempRequest, request_id)
    if temp_request is None:
        return {"error": "request_id not found"}, 404

    docs = [d for d in temp_request.documents if d.file_path]
    file_paths = [d.file_path for d in docs]
    doc_by_path = {d.file_path: d for d in docs}

    extraction_results = extract_batch(file_paths)

    summary = []
    for path, result in extraction_results.items():
        doc = doc_by_path[path]
        doc.extraction_status = result["status"]
        doc.extracted_text = result["text"]
        doc.extraction_error = result["error"]
        summary.append(
            {
                "document_id": str(doc.id),
                "file_path": path,
                "status": result["status"],
                "error": result["error"],
            }
        )

    db.commit()

    return {"request_id": request_id, "results": summary}


@app.post("/chunk-and-embed/{request_id}")
def chunk_and_embed(request_id: str, db: Session = Depends(get_db)):
    """Chunks every successfully-extracted document for this request and
    embeds all resulting chunks in one batched model call."""
    temp_request = db.get(TempRequest, request_id)
    if temp_request is None:
        return {"error": "request_id not found"}, 404

    summary = process_request_chunks_and_embeddings(db, temp_request)
    return {"request_id": request_id, **summary}


@app.post("/fetch-external/{request_id}")
def fetch_external(request_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Fetches external sources (website/catalog/tech_doc/digital_asset) for a
    request via the MCP server, and stores results in the SAME temp_documents
    table as uploaded files. Opt-in only: a source is fetched only if it's
    BOTH provided a URL in the request body AND present in the request's
    sources_selected — toggling a source off skips it entirely, even if a
    URL for it is included in the payload.

    Body shape: {"sources": {"website": "https://...", "catalog": "https://..."}}
    """
    temp_request = db.get(TempRequest, request_id)
    if temp_request is None:
        return {"error": "request_id not found"}, 404

    sources_urls = payload.get("sources", {})
    selected = set(temp_request.sources_selected or [])

    results = []
    for source_type, url in sources_urls.items():
        if source_type not in selected:
            results.append({"source_type": source_type, "url": url, "skipped": True, "reason": "not in sources_selected"})
            continue

        agent_result = call_source_agent(source_type, url)
        doc = TempDocument(
            temp_request_id=temp_request.id,
            source_type=source_type,
            external_url=url,
            extracted_text=agent_result.get("text"),
            extraction_status="success" if agent_result.get("text") else "failed",
            extraction_error=agent_result.get("error"),
        )
        db.add(doc)
        db.flush()
        results.append(
            {
                "source_type": source_type,
                "url": url,
                "skipped": False,
                "document_id": str(doc.id),
                "status": doc.extraction_status,
            }
        )

    db.commit()
    return {"request_id": request_id, "results": results}


@app.post("/orchestrate/{request_id}")
def orchestrate(request_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db)):
    """Runs the Supervisor graph: guardrails check, then only the sub-agents
    for this request's sources_selected. Body optionally provides
    {"urls": {"website": "https://..."}} for sources needing a fresh fetch —
    sources with no URL just use whatever's already in temp_chunks."""
    urls = payload.get("urls", {}) if payload else {}
    result = orchestrate_request(db, request_id, urls)
    return result


@app.post("/orchestrate-batch")
def orchestrate_batch_endpoint(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Concurrently orchestrates many requests at once — the real way to
    process the full hackathon dataset instead of one row at a time through
    the UI. Worker count follows the project's cores-2 rule.

    Body: either {"request_ids": [...]} or {"all_pending": true} to process
    every request that doesn't have a draft yet."""
    request_ids = payload.get("request_ids")

    if not request_ids and payload.get("all_pending"):
        rows = db.execute(select(TempRequest.id).where(~TempRequest.detected_products.any())).scalars().all()
        request_ids = [str(r) for r in rows]

    if not request_ids:
        return {"error": "Provide 'request_ids' (a list) or set 'all_pending': true"}

    return orchestrate_batch(request_ids)


@app.post("/import-dataset")
async def import_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bulk-imports the hackathon's input CSV — one TempRequest per row,
    mapping the 6 input columns directly and defaulting sources_selected to
    all 4 sources (the dataset gives no source preference)."""
    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    required_cols = {"Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"}
    if not required_cols.issubset(set(reader.fieldnames or [])):
        return {"error": f"CSV missing required columns. Expected: {sorted(required_cols)}"}

    created_ids = []
    for row in reader:
        query_text = f"{(row.get('Mfg_Part_Num') or '').strip()} {(row.get('Part_Desc') or '').strip()}".strip()
        temp_request = TempRequest(
            user_text=query_text,
            sources_selected=["website", "catalog", "tech_doc", "digital_asset"],
            mfg_part_num=row.get("Mfg_Part_Num"),
            part_desc=row.get("Part_Desc"),
            e1_brand=row.get("E1_Brand"),
            unilog_brand=row.get("Unilog_Brand"),
            dib_brand=row.get("DIB_Brand"),
            part_manuf=row.get("Part_Manuf"),
        )
        db.add(temp_request)
        db.flush()
        created_ids.append(str(temp_request.id))

    db.commit()
    return {"imported_count": len(created_ids), "request_ids": created_ids}


@app.get("/export/{request_id}")
def export_request(request_id: str, db: Session = Depends(get_db)):
    """Exports the most recent orchestration result for a request as a
    single-row CSV in the exact 252-column delivery format."""
    detected = (
        db.execute(
            select(TempDetectedProduct)
            .where(TempDetectedProduct.temp_request_id == request_id)
            .order_by(TempDetectedProduct.created_at.desc())
        )
        .scalars()
        .first()
    )
    if detected is None:
        return {"error": "No detected product for this request_id — run /orchestrate first"}

    attrs = (
        db.execute(select(TempProductAttribute).where(TempProductAttribute.temp_detected_product_id == detected.id))
        .scalars()
        .all()
    )
    attribute_rows = [
        {
            "attribute_type": a.attribute_type,
            "attribute_key": a.attribute_key,
            "attribute_value": a.attribute_value,
            "unit": a.unit,
        }
        for a in attrs
    ]

    core = {
        "mfg_part_num": detected.mfg_part_num,
        "part_desc": detected.part_desc,
        "e1_brand": detected.e1_brand,
        "unilog_brand": detected.unilog_brand,
        "dib_brand": detected.dib_brand,
        "part_manuf": detected.part_manuf,
        "manufacturer_name": detected.manufacturer_name,
        "title": detected.title,
    }
    row = build_delivery_row(core, detected.delivery_fields, attribute_rows)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=DELIVERY_COLUMNS)
    writer.writeheader()
    writer.writerow(row)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{request_id}.csv"'},
    )


@app.get("/export-all")
def export_all_products(db: Session = Depends(get_db)):
    """Exports every approved Main DB product as ONE multi-row CSV in the
    exact 252-column delivery format — this is the actual hackathon
    deliverable shape (all products together), not the single-row export
    above, which is for reviewing one product's result."""
    products = db.execute(select(Product).order_by(Product.created_at.asc())).scalars().all()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=DELIVERY_COLUMNS)
    writer.writeheader()

    for product in products:
        attrs = db.execute(select(ProductAttribute).where(ProductAttribute.product_id == product.id)).scalars().all()
        attribute_rows = [
            {
                "attribute_type": a.attribute_type,
                "attribute_key": a.attribute_key,
                "attribute_value": a.attribute_value,
                "unit": a.unit,
            }
            for a in attrs
        ]
        core = {
            "mfg_part_num": product.mfg_part_num,
            "part_desc": product.part_desc,
            "e1_brand": product.e1_brand,
            "unilog_brand": product.unilog_brand,
            "dib_brand": product.dib_brand,
            "part_manuf": product.part_manuf,
            "manufacturer_name": product.manufacturer_name,
            "title": product.title,
        }
        row = build_delivery_row(core, product.delivery_fields, attribute_rows)
        writer.writerow(row)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="delivery_export.csv"',
            "X-Row-Count": str(len(products)),
        },
    )


@app.post("/approve/{request_id}")
def approve(request_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db)):
    """Approves a request's draft product, transactionally moving it (plus
    its supporting documents/chunks/embeddings) into the Main DB. Body may
    optionally override fields the frontend let the user edit before
    approving: {"title", "manufacturer_name", "delivery_fields", "specs",
    "features"}."""
    result = approve_request(db, request_id, overrides=payload)
    return result


@app.get("/requests")
def list_requests(db: Session = Depends(get_db)):
    """Lists recent requests for the frontend's sidebar — newest first."""
    rows = db.execute(select(TempRequest).order_by(TempRequest.created_at.desc()).limit(100)).scalars().all()
    return {
        "requests": [
            {
                "request_id": str(r.id),
                "user_text": r.user_text,
                "mfg_part_num": r.mfg_part_num,
                "part_desc": r.part_desc,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "has_draft": len(r.detected_products) > 0,
            }
            for r in rows
        ]
    }


@app.get("/requests/{request_id}")
def get_request_detail(request_id: str, db: Session = Depends(get_db)):
    """Full detail for one request: raw fields + its latest draft (if any),
    including attributes — enough for the frontend to render and edit
    without needing to re-run orchestration."""
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

    draft = None
    if detected is not None:
        attrs = (
            db.execute(select(TempProductAttribute).where(TempProductAttribute.temp_detected_product_id == detected.id))
            .scalars()
            .all()
        )
        draft = {
            "detected_product_id": str(detected.id),
            "title": detected.title,
            "manufacturer_name": detected.manufacturer_name,
            "delivery_fields": detected.delivery_fields or {},
            "agent_provenance": detected.agent_provenance or {},
            "specs": [
                {
                    "key": a.attribute_key,
                    "value": a.attribute_value,
                    "uom": a.unit,
                    "confidence": a.confidence,
                    "conflicts": (a.extra or {}).get("conflicts", []),
                }
                for a in attrs
                if a.attribute_type == "spec"
            ],
            "features": [
                {"value": a.attribute_value, "confidence": a.confidence} for a in attrs if a.attribute_type == "feature"
            ],
        }

    return {
        "request_id": request_id,
        "user_text": temp_request.user_text,
        "sources_selected": temp_request.sources_selected or [],
        "mfg_part_num": temp_request.mfg_part_num,
        "part_desc": temp_request.part_desc,
        "e1_brand": temp_request.e1_brand,
        "unilog_brand": temp_request.unilog_brand,
        "dib_brand": temp_request.dib_brand,
        "part_manuf": temp_request.part_manuf,
        "status": temp_request.status,
        "draft": draft,
    }

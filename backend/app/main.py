import json
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import MEDIA_DIR
from app.db import check_db_connection
from app.deps import get_db
from app.extraction.batch import extract_batch
from app.mcp_client.client import call_source_agent
from app.models import TempDocument, TempRequest
from app.orchestration.service import orchestrate_request
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

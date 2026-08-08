import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.extraction.dispatcher import extract_file
from app.extraction.errors import ExtractionError

# Same 25MB ceiling as user uploads (see app/config.py) — external sources
# shouldn't get a more permissive limit than files the user uploads directly.
MAX_FETCH_BYTES = 25 * 1024 * 1024

CONTENT_TYPE_TO_EXT = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/html": ".html",
    "application/json": ".json",
    "text/csv": ".csv",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}

KNOWN_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".html", ".htm", ".json", ".csv", ".png", ".jpg", ".jpeg", ".txt"}


def _guess_extension(url: str, content_type: str | None) -> str:
    if content_type:
        base_ct = content_type.split(";")[0].strip().lower()
        if base_ct in CONTENT_TYPE_TO_EXT:
            return CONTENT_TYPE_TO_EXT[base_ct]

    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in KNOWN_EXTENSIONS:
        return suffix

    return ".html"  # most external sources without a clear signal are webpages


def fetch_and_extract(url: str, source_type: str) -> dict:
    """Downloads a URL and runs it through the SAME extraction pipeline as
    user-uploaded files (Phase 3) — a website, catalog PDF, tech doc, or
    digital asset all end up going through the identical extract->clean path.
    Returns {url, source_type, text, error} — error is None on success."""
    tmp_path = None
    try:
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            resp = client.get(url, headers={"User-Agent": "ProductIntelligenceAI/1.0"})
            resp.raise_for_status()
            content = resp.content
            content_type = resp.headers.get("content-type")
    except Exception as e:
        return {"url": url, "source_type": source_type, "text": None, "error": f"Fetch failed: {e}"}

    if len(content) > MAX_FETCH_BYTES:
        return {
            "url": url,
            "source_type": source_type,
            "text": None,
            "error": f"Fetched content exceeds {MAX_FETCH_BYTES // (1024*1024)}MB limit",
        }

    ext = _guess_extension(url, content_type)

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        text = extract_file(tmp_path)
        return {"url": url, "source_type": source_type, "text": text, "error": None}
    except ExtractionError as e:
        return {"url": url, "source_type": source_type, "text": None, "error": str(e)}
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

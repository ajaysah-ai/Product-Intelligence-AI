"""
Retrieval Agent (SYSTEM_DESIGN.md 1.3)

Input:  parsed query from Parser Agent
Output: ranked list of relevant chunks (top-k via pgvector cosine similarity)
Writes: source_documents, document_chunks

Never writes structured product fields — only raw evidence. Keeps
raw-vs-structured separation clean per the design doc.
"""

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.embeddings import embed_batch
from app.models import DocumentChunk, SourceDocument

CHUNK_SIZE = 800  # characters per chunk — tune during testing
CHUNK_OVERLAP = 100


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Simple sliding-window chunker. Swap for a smarter splitter
    (e.g. sentence-boundary aware) if extraction quality needs it."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


async def web_search(query: str, num_results: int = 5) -> list[dict]:
    """Search the web for candidate product pages.

    TODO: wire to your chosen SEARCH_PROVIDER (SerpAPI, Bing, etc.) using
    settings.search_api_key. Returns [] until an API key is configured —
    callers should fall back to mock data (see get_mock_chunks) when this
    returns nothing, per your "mock first, real later" plan.
    """
    if not settings.search_api_key:
        return []

    # Example shape for SerpAPI — adjust to whichever provider you pick.
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": settings.search_api_key, "num": num_results},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"url": r.get("link"), "title": r.get("title")}
            for r in data.get("organic_results", [])[:num_results]
        ]


async def fetch_page_text(url: str) -> str:
    """Fetch and extract visible text from a URL.

    Uses plain httpx + BeautifulSoup for static pages. For JS-rendered
    pages, swap this call for fetch_page_text_playwright() below —
    Playwright is heavier (spins up a browser) so use it selectively
    when a static fetch comes back empty/thin.
    """
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


async def fetch_page_text_playwright(url: str) -> str:
    """Fetch a JS-rendered page using Playwright. Use for sites that
    return little/no content via plain httpx (SPA product pages, etc.)."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=20000)
        content = await page.content()
        await browser.close()

    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def get_mock_chunks(brand: str, part_number: str) -> list[str]:
    """Fallback sample content for demo/testing when no search API key is
    configured, or when live results are thin. Replace/extend with real
    sample product pages relevant to your test set."""
    return [
        f"{brand} {part_number} is a professional-grade power tool. "
        f"Specifications: Power 750W, Voltage 220-240V, Disc Diameter 100mm, "
        f"No-load speed 11,000 RPM, Weight 1.8kg, Frequency 50/60Hz.",
        f"{brand} {part_number} features: compact body, ergonomic grip, "
        f"overload protection, high-speed motor, long carbon brush life, "
        f"easy disc replacement. Dimensions: 270 x 73 x 100mm.",
        f"{brand} {part_number} materials: housing ABS plastic, gear steel, "
        f"guard aluminium alloy, handle rubber grip. Applications: metal cutting, "
        f"pipe grinding, surface finishing, construction work. "
        f"Warranty: 1 year manufacturer warranty.",
    ]


async def retrieve_and_embed(
    db: AsyncSession,
    product_id,
    brand: str,
    part_number: str,
    use_mock_fallback: bool = True,
) -> list[dict]:
    """Full retrieval pipeline: search -> fetch -> chunk -> embed -> store.
    Returns the list of {source_document_id, chunk_text} dicts the
    Enrichment Agent will consume."""
    query = f"{brand} {part_number} specifications datasheet"
    results = await web_search(query)

    raw_texts: list[tuple[str, str]] = []  # (source_url, page_text)

    if results:
        for r in results:
            try:
                text = await fetch_page_text(r["url"])
                if len(text) < 200 and settings.use_playwright:
                    text = await fetch_page_text_playwright(r["url"])
                if text:
                    raw_texts.append((r["url"], text))
            except Exception:
                continue  # skip pages that fail to fetch; don't fail the whole run

    if not raw_texts and use_mock_fallback:
        mock_texts = get_mock_chunks(brand, part_number)
        raw_texts = [(f"mock://{brand}-{part_number}", t) for t in mock_texts]

    all_chunks_out: list[dict] = []

    for url, text in raw_texts:
        source_doc = SourceDocument(
            product_id=product_id,
            source_type="url" if not url.startswith("mock://") else "catalog",
            original_url=None if url.startswith("mock://") else url,
        )
        db.add(source_doc)
        await db.flush()

        pieces = chunk_text(text)
        if not pieces:
            continue
        embeddings = embed_batch(pieces)

        for piece, vec in zip(pieces, embeddings):
            chunk = DocumentChunk(
                source_document_id=source_doc.id,
                chunk_text=piece,
                embedding=vec,
            )
            db.add(chunk)
            all_chunks_out.append({"source_document_id": str(source_doc.id), "chunk_text": piece})

    await db.commit()
    return all_chunks_out


async def get_top_k_chunks(db: AsyncSession, query_text: str, k: int = 8) -> list[dict]:
    """Cosine-similarity search over document_chunks using pgvector."""
    from app.llm.embeddings import embed_text

    query_vec = embed_text(query_text)
    stmt = (
        select(DocumentChunk)
        .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
        .limit(k)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()
    return [
        {"source_document_id": str(c.source_document_id), "chunk_text": c.chunk_text}
        for c in chunks
    ]

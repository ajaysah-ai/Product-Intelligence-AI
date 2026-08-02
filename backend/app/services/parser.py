"""
Parser Agent (SYSTEM_DESIGN.md 1.2)

Input:  Part Number + Brand (+ optional description) OR image OR PDF
Output: {brand, part_number, description, input_type}
Writes: source_documents (raw input log), products (initial row, status='pending')
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, SourceDocument


async def parse_text_input(
    db: AsyncSession,
    brand: str,
    part_number: str,
    description: str | None,
    uploaded_by: str = "user",
) -> tuple[Product, SourceDocument]:
    """Handles the Part Number + Brand (+ description) input path.
    This is the fully-implemented path — image/PDF parsing are stubbed
    below pending vision-model wiring."""
    brand = brand.strip()
    part_number = part_number.strip()
    description = description.strip() if description else None

    product = Product(
        brand=brand,
        part_number=part_number,
        description_input=description,
        status="pending",
    )
    db.add(product)
    await db.flush()  # get product.id before creating the source_document

    source_doc = SourceDocument(
        product_id=product.id,
        source_type="catalog",  # a Part#+Brand text submission counts as a catalog-style input
        uploaded_by=uploaded_by,
    )
    db.add(source_doc)
    await db.flush()

    await db.commit()
    await db.refresh(product)
    await db.refresh(source_doc)
    return product, source_doc


async def parse_image_input(db: AsyncSession, file_path: str, uploaded_by: str = "user"):
    """TODO: call a vision-language model to extract visible brand/model/text
    from the uploaded image, then fall through to parse_text_input() with
    whatever was recognized. Requires a VLM-capable model — Groq's
    openai/gpt-oss-120b is text-only, so this needs a vision model added
    to config (e.g. via OmniRoute) before this path is wired up."""
    raise NotImplementedError("Image input parsing needs a vision-language model — not yet wired.")


async def parse_pdf_input(db: AsyncSession, file_path: str, uploaded_by: str = "user"):
    """TODO: extract text via pypdf (with OCR fallback for scanned PDFs),
    then either treat it as a source document for RAG directly, or run a
    light extraction pass to identify brand/part_number if present."""
    raise NotImplementedError("PDF input parsing not yet wired — see pypdf extraction TODO.")

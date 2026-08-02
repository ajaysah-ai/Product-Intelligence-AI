"""
Image search/reference service.

TODO: wire to a product image source (official manufacturer image URLs
scraped via retrieval.py, or a reverse-image/product-image search API).
For the hackathon demo, this can start by pulling the first product image
found on the pages already fetched by the Retrieval Agent, tagged as
view_type='official_link' with just the external_url populated — actual
front/side/packaging classification can come later.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProductImage


async def save_image_reference(
    db: AsyncSession,
    product_id: uuid.UUID,
    view_type: str,
    file_path: str | None = None,
    external_url: str | None = None,
    source_document_id: uuid.UUID | None = None,
) -> ProductImage:
    image = ProductImage(
        product_id=product_id,
        view_type=view_type,
        file_path=file_path,
        external_url=external_url,
        source_document_id=source_document_id,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return image

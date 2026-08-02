from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import UploadRequest, UploadResponse
from app.services import parser

router = APIRouter(prefix="/api/v1", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_product(payload: UploadRequest, db: AsyncSession = Depends(get_db)):
    if not payload.brand or not payload.part_number:
        # Image/PDF upload paths aren't wired yet — see services/parser.py TODOs.
        raise HTTPException(
            status_code=400,
            detail="Only Brand + Part Number input is currently supported. "
                   "Image/PDF upload needs a vision-language model — coming next.",
        )

    product, source_doc = await parser.parse_text_input(
        db, brand=payload.brand, part_number=payload.part_number, description=payload.description
    )
    return UploadResponse(product_id=product.id, status=product.status, source_document_id=source_doc.id)

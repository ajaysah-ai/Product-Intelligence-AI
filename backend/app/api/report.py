import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.product import get_product
from app.database import get_db

router = APIRouter(prefix="/api/v1/products", tags=["report"])


@router.get("/{product_id}/report")
async def get_report(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Full joined report for a product — reuses get_product() since the
    same structured payload works for both the UI and a demo export.
    Swap for a PDF/formatted export once the demo needs one."""
    return await get_product(product_id, db)

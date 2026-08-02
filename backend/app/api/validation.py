import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Product, ProductSpec, ValidationLog
from app.schemas import ReviewRequest

router = APIRouter(prefix="/api/v1/products", tags=["validation"])


@router.get("/{product_id}/validation-logs")
async def get_validation_logs(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    logs = (
        await db.execute(select(ValidationLog).where(ValidationLog.product_id == product_id))
    ).scalars().all()
    return [
        {
            "field_name": l.field_name,
            "old_value": l.old_value,
            "new_value": l.new_value,
            "validation_type": l.validation_type,
            "passed": l.passed,
            "notes": l.notes,
            "created_at": l.created_at,
        }
        for l in logs
    ]


@router.post("/{product_id}/review")
async def submit_review(product_id: uuid.UUID, payload: ReviewRequest, db: AsyncSession = Depends(get_db)):
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Currently only handles spec field corrections — extend for
    # features/materials/applications/warranty as those review flows are needed.
    spec = (
        await db.execute(
            select(ProductSpec).where(
                ProductSpec.product_id == product_id, ProductSpec.spec_name == payload.field_name
            )
        )
    ).scalars().first()

    old_value = spec.spec_value if spec else None
    if spec:
        spec.spec_value = payload.new_value
        spec.confidence = 100  # human-confirmed
        spec.extraction_method = "manual_override"

    db.add(ValidationLog(
        product_id=product_id,
        field_name=payload.field_name,
        old_value=old_value,
        new_value=payload.new_value,
        validation_type="human_review",
        passed=True,
        notes=f"Reviewed by {payload.reviewer}",
    ))
    await db.commit()
    return {"status": "ok", "field_name": payload.field_name, "new_value": payload.new_value}

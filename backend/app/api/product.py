import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.llm import agent
from app.models import (
    AgentState,
    Product,
    ProductApplication,
    ProductDimension,
    ProductFeature,
    ProductImage,
    ProductMaterial,
    ProductSpec,
    ProductWarranty,
)
from app.schemas import (
    ApplicationOut,
    ConfidenceResponse,
    DimensionsOut,
    EnrichResponse,
    FeatureOut,
    FieldConfidence,
    ImageOut,
    MaterialOut,
    ProductOut,
    SpecOut,
    StatusResponse,
    WarrantyOut,
)

router = APIRouter(prefix="/api/v1/products", tags=["products"])


async def _get_product_or_404(db: AsyncSession, product_id: uuid.UUID) -> Product:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


async def _run_pipeline_background(product_id: uuid.UUID):
    """Runs in a fresh DB session since BackgroundTasks execute after the
    request's own session has closed."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalars().first()
        if product:
            await agent.run_pipeline(db, product)


@router.post("/{product_id}/enrich", response_model=EnrichResponse)
async def enrich_product(product_id: uuid.UUID, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    product = await _get_product_or_404(db, product_id)
    product.status = "processing"
    await db.commit()

    background_tasks.add_task(_run_pipeline_background, product_id)

    return EnrichResponse(product_id=product.id, status="processing", agent_run_id=uuid.uuid4())


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    product = await _get_product_or_404(db, product_id)

    specs = (await db.execute(select(ProductSpec).where(ProductSpec.product_id == product_id))).scalars().all()
    features = (await db.execute(select(ProductFeature).where(ProductFeature.product_id == product_id))).scalars().all()
    dims = (await db.execute(select(ProductDimension).where(ProductDimension.product_id == product_id))).scalars().first()
    materials = (await db.execute(select(ProductMaterial).where(ProductMaterial.product_id == product_id))).scalars().all()
    applications = (await db.execute(select(ProductApplication).where(ProductApplication.product_id == product_id))).scalars().all()
    warranty = (await db.execute(select(ProductWarranty).where(ProductWarranty.product_id == product_id))).scalars().first()
    images = (await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))).scalars().all()

    return ProductOut(
        product_id=product.id,
        title=product.title,
        status=product.status,
        overall_confidence=float(product.overall_confidence) if product.overall_confidence is not None else None,
        specs=[SpecOut(spec_name=s.spec_name, spec_value=s.spec_value, spec_unit=s.spec_unit,
                        confidence=s.confidence, source_document_id=s.source_document_id) for s in specs],
        features=[FeatureOut(feature_text=f.feature_text, confidence=f.confidence,
                              source_document_id=f.source_document_id) for f in features],
        dimensions=DimensionsOut(
            length_mm=dims.length_mm, width_mm=dims.width_mm, height_mm=dims.height_mm,
            weight_kg=dims.weight_kg, confidence=dims.confidence, source_document_id=dims.source_document_id,
        ) if dims else None,
        materials=[MaterialOut(component=m.component, material=m.material,
                                source_document_id=m.source_document_id) for m in materials],
        applications=[ApplicationOut(application_text=a.application_text,
                                      source_document_id=a.source_document_id) for a in applications],
        warranty=WarrantyOut(
            duration_text=warranty.duration_text, registration_required=warranty.registration_required,
            confidence=warranty.confidence, source_document_id=warranty.source_document_id,
        ) if warranty else None,
        images=[ImageOut(view_type=i.view_type, file_path=i.file_path, external_url=i.external_url,
                          source_document_id=i.source_document_id) for i in images],
    )


@router.get("/{product_id}/confidence", response_model=ConfidenceResponse)
async def get_confidence(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    product = await _get_product_or_404(db, product_id)
    specs = (await db.execute(select(ProductSpec).where(ProductSpec.product_id == product_id))).scalars().all()

    fields = [FieldConfidence(field=s.spec_name, confidence=float(s.confidence)) for s in specs if s.confidence is not None]
    review = [f.field for f in fields if f.confidence < 60]

    return ConfidenceResponse(
        overall_confidence=float(product.overall_confidence) if product.overall_confidence is not None else None,
        fields=fields,
        needs_review=review,
    )


@router.get("/{product_id}/status", response_model=StatusResponse)
async def get_status(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    product = await _get_product_or_404(db, product_id)
    latest_state = (
        await db.execute(
            select(AgentState)
            .where(AgentState.product_id == product_id)
            .order_by(AgentState.created_at.desc())
        )
    ).scalars().first()

    from app.llm.agent import STEPS
    progress = STEPS.index(latest_state.agent_name) + 1 if latest_state and latest_state.agent_name in STEPS else 0

    return StatusResponse(
        status=product.status,
        current_agent=latest_state.agent_name if latest_state else None,
        progress=progress,
        total_steps=len(STEPS),
    )

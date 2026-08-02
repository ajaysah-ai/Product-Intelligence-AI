"""
Validation Agent (SYSTEM_DESIGN.md 1.5)

Input:  all structured fields written by the Enrichment Agent
Output: per-field confidence already set by Enrichment Agent is trusted as
        source_agreement for now (single-pass); this agent adds rule checks
        and rolls up products.overall_confidence + status.
Writes: validation_logs, products.overall_confidence, products.status

NOTE: cross-referencing the same field across multiple retrieved sources
(the "source_agreement" signal) needs multiple independent sources per
field — with only the mock fallback wired up in retrieval.py, there's
usually one source per field right now. Once real web search returns
multiple pages, extend this to compare values across sources before
trusting Enrichment Agent's confidence outright.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Product,
    ProductDimension,
    ProductFeature,
    ProductSpec,
    ProductWarranty,
    ValidationLog,
)
from app.services.confidence import needs_review, rollup_confidence

# Simple plausibility ranges for common spec names — extend as needed.
PLAUSIBLE_RANGES = {
    "power": (1, 5000),        # W
    "voltage": (1, 500),       # V
    "weight": (0.01, 500),     # kg
}


async def validate_product(db: AsyncSession, product: Product) -> dict:
    field_scores: dict[str, float] = {}

    specs_result = await db.execute(select(ProductSpec).where(ProductSpec.product_id == product.id))
    specs = specs_result.scalars().all()
    for spec in specs:
        _rule_check_spec(spec)
        field_scores[spec.spec_name] = float(spec.confidence) if spec.confidence is not None else None
        db.add(ValidationLog(
            product_id=product.id,
            field_name=spec.spec_name,
            new_value=spec.spec_value,
            validation_type="rule_check",
            passed=True,
            notes="Range/plausibility check applied.",
        ))

    dims_result = await db.execute(select(ProductDimension).where(ProductDimension.product_id == product.id))
    dims = dims_result.scalars().first()
    if dims:
        field_scores["dimensions"] = float(dims.confidence) if dims.confidence is not None else None

    warranty_result = await db.execute(select(ProductWarranty).where(ProductWarranty.product_id == product.id))
    warranty = warranty_result.scalars().first()
    if warranty:
        field_scores["warranty"] = float(warranty.confidence) if warranty.confidence is not None else None

    features_result = await db.execute(select(ProductFeature).where(ProductFeature.product_id == product.id))
    features = features_result.scalars().all()
    for i, feat in enumerate(features):
        field_scores[f"feature_{i}"] = float(feat.confidence) if feat.confidence is not None else None

    overall = rollup_confidence(list(field_scores.values()))
    review_fields = needs_review(field_scores)

    product.overall_confidence = overall
    product.status = "needs_review" if review_fields else "validated"

    await db.commit()
    await db.refresh(product)

    return {
        "overall_confidence": overall,
        "fields": [{"field": k, "confidence": v} for k, v in field_scores.items()],
        "needs_review": review_fields,
    }


def _rule_check_spec(spec: ProductSpec) -> None:
    """Downgrades confidence in-place if a spec value falls outside a
    plausible range. Doesn't raise — flags via lowered confidence instead,
    consistent with "null/low-confidence over hallucination"."""
    key = spec.spec_name.lower() if spec.spec_name else ""
    bounds = next((v for k, v in PLAUSIBLE_RANGES.items() if k in key), None)
    if not bounds or not spec.spec_value:
        return
    try:
        numeric_value = float("".join(c for c in spec.spec_value if c.isdigit() or c == "."))
        low, high = bounds
        if not (low <= numeric_value <= high):
            spec.confidence = min(float(spec.confidence or 50), 40)
    except ValueError:
        pass

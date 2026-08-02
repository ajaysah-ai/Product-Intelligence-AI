"""
Enrichment Agent (SYSTEM_DESIGN.md 1.4)

Input:  top-k chunks from Retrieval Agent + product identity from Parser Agent
Output: structured JSON matching the extraction contract (SYSTEM_DESIGN.md Part 2)
Writes: product_specs, product_features, product_dimensions, product_materials,
        product_applications, product_warranty (product_images handled separately
        by services/image_search.py)

Guardrail: null + low confidence beats a hallucinated value — enforced via
the prompts' "answer null if not found" instruction plus the retry-once
behavior below.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import prompts
from app.llm.client import chat_completion_json
from app.models import (
    Product,
    ProductApplication,
    ProductDimension,
    ProductFeature,
    ProductMaterial,
    ProductSpec,
    ProductWarranty,
)


async def _call_with_retry(prompt_fn, product_identity: dict, chunks: list[dict], retries: int = 1) -> dict:
    messages = prompt_fn(product_identity, chunks)
    last_error = None
    for attempt in range(retries + 1):
        try:
            return await chat_completion_json(messages)
        except ValueError as exc:
            last_error = exc
            continue
    # After exhausting retries, return an empty result rather than crashing
    # the whole pipeline over one failed field-group.
    return {}


async def enrich_product(db: AsyncSession, product: Product, chunks: list[dict]) -> dict:
    """Runs all field-group extractions and persists results.
    Returns the combined structured dict for the response payload."""
    identity = {
        "brand": product.brand,
        "part_number": product.part_number,
        "description": product.description_input or "",
    }

    title_result = await _call_with_retry(prompts.title_prompt, identity, chunks)
    specs_result = await _call_with_retry(prompts.specs_prompt, identity, chunks)
    features_result = await _call_with_retry(prompts.features_prompt, identity, chunks)
    dimensions_result = await _call_with_retry(prompts.dimensions_prompt, identity, chunks)
    materials_result = await _call_with_retry(prompts.materials_prompt, identity, chunks)
    applications_result = await _call_with_retry(prompts.applications_prompt, identity, chunks)
    warranty_result = await _call_with_retry(prompts.warranty_prompt, identity, chunks)

    if title_result.get("title"):
        product.title = title_result["title"]

    for s in specs_result.get("specs", []):
        db.add(ProductSpec(
            product_id=product.id,
            spec_name=s.get("spec_name"),
            spec_value=s.get("spec_value"),
            spec_unit=s.get("spec_unit"),
            confidence=s.get("confidence"),
            source_document_id=_safe_uuid(s.get("source_document_id")),
            extraction_method="llm_extraction",
        ))

    for f in features_result.get("features", []):
        db.add(ProductFeature(
            product_id=product.id,
            feature_text=f.get("feature_text"),
            confidence=f.get("confidence"),
            source_document_id=_safe_uuid(f.get("source_document_id")),
        ))

    dims = dimensions_result.get("dimensions")
    if dims:
        db.add(ProductDimension(
            product_id=product.id,
            length_mm=dims.get("length_mm"),
            width_mm=dims.get("width_mm"),
            height_mm=dims.get("height_mm"),
            weight_kg=dims.get("weight_kg"),
            confidence=dims.get("confidence"),
            source_document_id=_safe_uuid(dims.get("source_document_id")),
        ))

    for m in materials_result.get("materials", []):
        db.add(ProductMaterial(
            product_id=product.id,
            component=m.get("component"),
            material=m.get("material"),
            source_document_id=_safe_uuid(m.get("source_document_id")),
        ))

    for a in applications_result.get("applications", []):
        db.add(ProductApplication(
            product_id=product.id,
            application_text=a.get("application_text"),
            source_document_id=_safe_uuid(a.get("source_document_id")),
        ))

    warranty = warranty_result.get("warranty")
    if warranty:
        db.add(ProductWarranty(
            product_id=product.id,
            duration_text=warranty.get("duration_text"),
            registration_required=warranty.get("registration_required"),
            confidence=warranty.get("confidence"),
            source_document_id=_safe_uuid(warranty.get("source_document_id")),
        ))

    product.status = "processing"  # Validation Agent moves this to validated/needs_review
    await db.commit()

    return {
        "title": title_result.get("title"),
        "specs": specs_result.get("specs", []),
        "features": features_result.get("features", []),
        "dimensions": dims,
        "materials": materials_result.get("materials", []),
        "applications": applications_result.get("applications", []),
        "warranty": warranty,
    }


def _safe_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None

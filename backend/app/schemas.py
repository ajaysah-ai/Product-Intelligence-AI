import uuid

from pydantic import BaseModel


# ---------- 3.1 Upload ----------
class UploadRequest(BaseModel):
    brand: str | None = None
    part_number: str | None = None
    description: str | None = None


class UploadResponse(BaseModel):
    product_id: uuid.UUID
    status: str
    source_document_id: uuid.UUID


# ---------- 3.2 Enrich ----------
class EnrichResponse(BaseModel):
    product_id: uuid.UUID
    status: str
    agent_run_id: uuid.UUID


# ---------- Part 2 extraction JSON contract ----------
class SpecOut(BaseModel):
    spec_name: str
    spec_value: str | None = None
    spec_unit: str | None = None
    confidence: float | None = None
    source_document_id: uuid.UUID | None = None


class FeatureOut(BaseModel):
    feature_text: str
    confidence: float | None = None
    source_document_id: uuid.UUID | None = None


class DimensionsOut(BaseModel):
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    weight_kg: float | None = None
    confidence: float | None = None
    source_document_id: uuid.UUID | None = None


class MaterialOut(BaseModel):
    component: str
    material: str
    source_document_id: uuid.UUID | None = None


class ApplicationOut(BaseModel):
    application_text: str
    source_document_id: uuid.UUID | None = None


class WarrantyOut(BaseModel):
    duration_text: str | None = None
    registration_required: bool | None = None
    confidence: float | None = None
    source_document_id: uuid.UUID | None = None


class ImageOut(BaseModel):
    view_type: str | None = None
    file_path: str | None = None
    external_url: str | None = None
    source_document_id: uuid.UUID | None = None


class ProductOut(BaseModel):
    product_id: uuid.UUID
    title: str | None = None
    status: str
    overall_confidence: float | None = None
    specs: list[SpecOut] = []
    features: list[FeatureOut] = []
    dimensions: DimensionsOut | None = None
    materials: list[MaterialOut] = []
    applications: list[ApplicationOut] = []
    warranty: WarrantyOut | None = None
    images: list[ImageOut] = []


# ---------- 3.4 Confidence ----------
class FieldConfidence(BaseModel):
    field: str
    confidence: float


class ConfidenceResponse(BaseModel):
    overall_confidence: float | None = None
    fields: list[FieldConfidence] = []
    needs_review: list[str] = []


# ---------- 3.5 Review ----------
class ReviewRequest(BaseModel):
    field_name: str
    new_value: str
    reviewer: str


# ---------- 3.7 Status ----------
class StatusResponse(BaseModel):
    status: str
    current_agent: str | None = None
    progress: int | None = None
    total_steps: int | None = None

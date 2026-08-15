import os
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Embedding dimension is configurable — 384 matches all-MiniLM-L6-v2 (CPU-friendly).
# Change via .env if you pick a different embedding model in Phase 4.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))


def _uuid_col():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now():
    return datetime.now(timezone.utc)


SOURCE_TYPES = ("website", "catalog", "tech_doc", "digital_asset", "user_upload")
REQUEST_STATUSES = ("pending", "processing", "awaiting_approval", "approved", "rejected")
DETECTED_PRODUCT_STATUSES = ("draft", "awaiting_approval", "approved", "rejected")
ATTRIBUTE_TYPES = ("spec", "feature", "dimension", "material", "application", "warranty", "image")


# ---------------------------------------------------------------------------
# MAIN SCHEMA — approved, permanent data
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "products"

    id = _uuid_col()
    title = Column(Text, nullable=False)
    source_request_id = Column(UUID(as_uuid=True), nullable=True)  # traceability only, no FK (temp rows get cleaned up)

    # Core fields from the hackathon delivery format (see app/delivery/schema.py) —
    # passthrough from the input dataset, plus the researched manufacturer name.
    mfg_part_num = Column(Text, nullable=True)
    part_desc = Column(Text, nullable=True)
    e1_brand = Column(Text, nullable=True)
    unilog_brand = Column(Text, nullable=True)
    dib_brand = Column(Text, nullable=True)
    part_manuf = Column(Text, nullable=True)
    manufacturer_name = Column(Text, nullable=True)

    # The ~75 long-tail delivery columns (URLs, descriptions, dimensions,
    # documents, images, identifiers) that don't need their own DB column —
    # keyed by the EXACT delivery column name, e.g. delivery_fields["MFR URL"].
    delivery_fields = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    documents = relationship("Document", back_populates="product", cascade="all, delete-orphan")
    attributes = relationship("ProductAttribute", back_populates="product", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = _uuid_col()
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    source_type = Column(Enum(*SOURCE_TYPES, name="source_type_enum"), nullable=False)
    file_path = Column(Text, nullable=True)
    external_url = Column(Text, nullable=True)
    mime_type = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=True)
    extraction_status = Column(Text, nullable=True, default="pending")  # pending/success/failed
    extraction_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    product = relationship("Product", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id = _uuid_col()
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    document = relationship("Document", back_populates="chunks")
    embedding = relationship("Embedding", back_populates="chunk", uselist=False, cascade="all, delete-orphan")


class Embedding(Base):
    __tablename__ = "embeddings"

    id = _uuid_col()
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    vector = Column(Vector(EMBEDDING_DIM), nullable=False)
    model_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("chunk_id", name="uq_embeddings_chunk_id"),)

    chunk = relationship("Chunk", back_populates="embedding")


class ProductAttribute(Base):
    """EAV-style table: one row per spec/feature/dimension/material/application/warranty/image field.
    attribute_type discriminates which kind; extra (JSONB) holds fields that don't fit key/value/unit
    (e.g. external_url, file_path, registration_required, weight_kg)."""

    __tablename__ = "product_attributes"

    id = _uuid_col()
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    attribute_type = Column(Enum(*ATTRIBUTE_TYPES, name="attribute_type_enum"), nullable=False)
    attribute_key = Column(Text, nullable=True)
    attribute_value = Column(Text, nullable=True)
    unit = Column(Text, nullable=True)
    confidence = Column(Integer, nullable=True)  # 0-100
    extra = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    product = relationship("Product", back_populates="attributes")


# ---------------------------------------------------------------------------
# TEMP SCHEMA — draft data pending human approval (Phase 9 clears these on approve)
# ---------------------------------------------------------------------------

class TempRequest(Base):
    __tablename__ = "temp_requests"

    id = _uuid_col()
    user_text = Column(Text, nullable=True)
    sources_selected = Column(JSONB, nullable=True)  # e.g. ["website", "catalog"]

    # Raw input-dataset columns (see app/delivery/schema.py PASSTHROUGH_COLUMNS)
    # — set at bulk-import time, copied into TempDetectedProduct at orchestration time.
    mfg_part_num = Column(Text, nullable=True)
    part_desc = Column(Text, nullable=True)
    e1_brand = Column(Text, nullable=True)
    unilog_brand = Column(Text, nullable=True)
    dib_brand = Column(Text, nullable=True)
    part_manuf = Column(Text, nullable=True)

    status = Column(Enum(*REQUEST_STATUSES, name="request_status_enum"), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    documents = relationship("TempDocument", back_populates="request", cascade="all, delete-orphan")
    detected_products = relationship("TempDetectedProduct", back_populates="request", cascade="all, delete-orphan")


class TempDocument(Base):
    __tablename__ = "temp_documents"

    id = _uuid_col()
    temp_request_id = Column(UUID(as_uuid=True), ForeignKey("temp_requests.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(Enum(*SOURCE_TYPES, name="source_type_enum"), nullable=False)
    file_path = Column(Text, nullable=True)
    external_url = Column(Text, nullable=True)
    mime_type = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=True)
    extraction_status = Column(Text, nullable=True, default="pending")  # pending/success/failed
    extraction_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    request = relationship("TempRequest", back_populates="documents")
    chunks = relationship("TempChunk", back_populates="document", cascade="all, delete-orphan")


class TempChunk(Base):
    __tablename__ = "temp_chunks"

    id = _uuid_col()
    temp_document_id = Column(UUID(as_uuid=True), ForeignKey("temp_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    document = relationship("TempDocument", back_populates="chunks")
    embedding = relationship("TempEmbedding", back_populates="chunk", uselist=False, cascade="all, delete-orphan")


class TempEmbedding(Base):
    __tablename__ = "temp_embeddings"

    id = _uuid_col()
    temp_chunk_id = Column(UUID(as_uuid=True), ForeignKey("temp_chunks.id", ondelete="CASCADE"), nullable=False)
    vector = Column(Vector(EMBEDDING_DIM), nullable=False)
    model_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("temp_chunk_id", name="uq_temp_embeddings_chunk_id"),)

    chunk = relationship("TempChunk", back_populates="embedding")


class TempDetectedProduct(Base):
    """The AI's draft product object for a request, awaiting human approval (Phase 8/9)."""

    __tablename__ = "temp_detected_products"

    id = _uuid_col()
    temp_request_id = Column(UUID(as_uuid=True), ForeignKey("temp_requests.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=True)

    # Mirrors Product's core delivery-format fields (see app/delivery/schema.py)
    # so Phase 9's approval step can copy these straight across.
    mfg_part_num = Column(Text, nullable=True)
    part_desc = Column(Text, nullable=True)
    e1_brand = Column(Text, nullable=True)
    unilog_brand = Column(Text, nullable=True)
    dib_brand = Column(Text, nullable=True)
    part_manuf = Column(Text, nullable=True)
    manufacturer_name = Column(Text, nullable=True)
    delivery_fields = Column(JSONB, nullable=True)

    status = Column(Enum(*DETECTED_PRODUCT_STATUSES, name="detected_product_status_enum"), default="draft", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    request = relationship("TempRequest", back_populates="detected_products")
    attributes = relationship("TempProductAttribute", back_populates="detected_product", cascade="all, delete-orphan")


class TempProductAttribute(Base):
    __tablename__ = "temp_product_attributes"

    id = _uuid_col()
    temp_detected_product_id = Column(
        UUID(as_uuid=True), ForeignKey("temp_detected_products.id", ondelete="CASCADE"), nullable=False
    )
    attribute_type = Column(Enum(*ATTRIBUTE_TYPES, name="attribute_type_enum"), nullable=False)
    attribute_key = Column(Text, nullable=True)
    attribute_value = Column(Text, nullable=True)
    unit = Column(Text, nullable=True)
    confidence = Column(Integer, nullable=True)
    extra = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    detected_product = relationship("TempDetectedProduct", back_populates="attributes")

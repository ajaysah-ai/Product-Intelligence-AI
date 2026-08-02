-- Product Intelligence  AI - Database
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- source_documents - Record of each input (Image/PDF/URL/catalog)
CREATE TABLE source_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID,
    source_type TEXT NOT NULL CHECK (source_type IN ('pdf', 'image', 'url', 'catalog')),
    file_path TEXT,
    original_url TEXT,
    uploaded_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- products - core entity
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brand TEXT NOT NULL,
    part_number TEXT NOT NULL,
    title TEXT,
    product_type TEXT,
    description_input TEXT,
    overall_confidence NUMERIC(5,2),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'validated', 'needs_review', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (brand, part_number)
);

-- Now making source_documents.product_id as FK
ALTER TABLE source_documents
    ADD CONSTRAINT fk_source_documents_product
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE;

-- product_specs - key/value specifications (power, voltage, etc.)
CREATE TABLE product_specs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    spec_name TEXT NOT NULL,
    spec_value TEXT,
    spec_unit TEXT,
    confidence NUMERIC(5,2),
    source_document_id UUID REFERENCES source_documents(id),
    extraction_method TEXT CHECK (extraction_method IN ('llm_extraction', 'regex', 'manual_override'))
);
CREATE INDEX idx_product_specs_product_id ON product_specs(product_id);

-- product_dimensions = physical measurements
CREATE TABLE product_dimensions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    length_mm NUMERIC,
    width_mm NUMERIC,
    height_mm NUMERIC,
    weight_kg NUMERIC,
    confidence NUMERIC(5,2),
    source_document_id UUID REFERENCES source_documents(id)
);
CREATE INDEX idx_product_dimensions_product_id ON product_dimensions(product_id);
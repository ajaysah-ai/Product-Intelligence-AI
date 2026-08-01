-- Product Intelligence AI - Database Schema
-- PostgreSQL 16 + pgvector
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. source_documents - root of traceability
CREATE TABLE source_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID, -- FK added after products exists
    source_type TEXT NOT NULL CHECK (source_type IN ('pdf', 'image', 'url', 'catalog')),
    file_path TEXT,
    original_url TEXT,
    uploaded_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. products - core entity
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brand TEXT NOT NULL,
    part_number TEXT NOT NULL,
    title TEXT,
    product_type TEXT,
    description_input TEXT,
    overall_confidence NUMERIC(5, 2),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'validated', 'needs_review', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (brand, part_number)
);
ALTER TABLE source_documents ADD CONSTRAINT fk_source_documents_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE;

-- 3. product_specs - key/value specifications
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

-- 4. product_dimensions
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

--5. product_materials
CREATE TABLE product_materials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) DELETE ON CASCADE,
    component TEXT NOT NULL,
    material TEXT NOT NULL,
    source_document_id UUID REFERENCES source_documents(id)
);
CREATE INDEX idx_product_materials_product_id ON product_materials(product_id);

-- 6. product_features
CREATE TABLE product_features (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    feature_text TEXT NOT NULL,
    confidence NUMERIC(5,2),
    source_document_id UUID REFERENCES source_documents(id)

);
CREATE INDEX idx_product_features_product_id ON product_features(product_id);

-- 7. product_applications
CREATE TABLE product_applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    application_text TEXT NOT NULL,
    source_document_id UUID REFERENCES source_documents(id)

);
CREATE INDEX idx_product_applications_product_id ON product_applications(product_id);

-- 8. product_warranty
CREATE TABLE product_warranty (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    duration_text TEXT,
    registration_required BOOLEAN,
    confidence NUMERIC(5,2),
    source_document_id UUID REFERENCES source_documents(id)
);
CREATE INDEX idx_product_warranty_product_id ON product_warranty(product_id);

-- 9. product_images - metadata only; files live in the media volume
CREATE TABLE product_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    view_type TEXT CHECK (view_type IN ('front', 'side', 'packaging', 'official_link', 'other')),
    file_path TEXT,
    external_url TEXT,
    source_document_id UUID REFERENCES source_documents(id)

);
CREATE INDEX idx_product_images_product_id ON product_images(product_id);

-- 10. document_chunks - RAG (pgvector)
-- Embedding dimension = 384, matching a local sentence-transformers
-- model (all-MiniLM-L6-v2), since Groq does not serve an embeddings endpoint.
-- Change the dimension here if you switch embedding models.
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,

    chunk_text TEXT NOT NULL,
    page_ref INTEGER,
    embedding VECTOR(384),
    created_at TIMESTAMPTZ NOT NUll  DEFAULT now()
);
CREATE INDEX idx_document_chunks_source_doc ON document_chunks(source_document_id);
CREATE INDEX idx_document_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 11. agent_state - multi-agent working memory
CREATE TABLE agent_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL CHECK (agent_name IN ('orchestrator', 'parser_agent', 'retrieval_agent', 'enrichment_agent', 'validation_agent')),
    state_data JSONB,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_state_product_id ON agent_state(product_id);

-- 12. validation_logs - audit trail
CREATE TABLE validation_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    validation_type TEXT CHECK (validation_type IN ('cross_reference', 'human_review', 'rule_check')),
    passed BOOLEAN,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_validation_logs_product_id ON validation_logs(product_id);

-- updated_at auto-touch trigger (products, agent_state)
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER trg_agent_state_updated_at
    BEFORE UPDATE ON agent_state
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

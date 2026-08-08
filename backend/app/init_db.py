"""
Run once per fresh database:
    docker compose exec backend python -m app.init_db
"""
from sqlalchemy import text

from app.db import engine
from app.models import Base


def init_db():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
        print("[ok] vector extension ready")

    Base.metadata.create_all(engine)
    print(f"[ok] created/verified {len(Base.metadata.tables)} tables:")
    for name in sorted(Base.metadata.tables.keys()):
        print(f"     - {name}")

    # Idempotent migration: safe to re-run against an already-populated DB from
    # earlier phases. create_all() only creates NEW tables, it never alters
    # existing ones, so new columns on existing tables are added here instead.
    migration_statements = [
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_text TEXT",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_status TEXT DEFAULT 'pending'",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_error TEXT",
        "ALTER TABLE temp_documents ADD COLUMN IF NOT EXISTS extracted_text TEXT",
        "ALTER TABLE temp_documents ADD COLUMN IF NOT EXISTS extraction_status TEXT DEFAULT 'pending'",
        "ALTER TABLE temp_documents ADD COLUMN IF NOT EXISTS extraction_error TEXT",
    ]
    with engine.connect() as conn:
        for stmt in migration_statements:
            conn.execute(text(stmt))
        conn.commit()
    print("[ok] schema migration applied (extraction columns)")


if __name__ == "__main__":
    init_db()

import math

from sqlalchemy import select

from app.db import SessionLocal
from app.mcp_client.client import call_source_agent
from app.models import ProductAttribute, TempDocument, TempRequest
from app.orchestration.hybrid_rag import hybrid_rag_retrieve
from app.orchestration.llm import normalize_chunks
from app.orchestration.web_search import search_web
from app.services.chunk_embed_service import process_request_chunks_and_embeddings

# Search query template per source — used by the Planner when no explicit
# URL is provided and this source has no data yet for this request.
SEARCH_QUERY_TEMPLATES = {
    "website": "{query} official product page",
    "catalog": "{query} product catalog",
    "tech_doc": "{query} spec sheet datasheet manual pdf",
    "digital_asset": "{query} product image",
}


def run_sub_agent(source_type: str, temp_request_id: str, user_text: str, url: str | None) -> dict:
    """Runs one full sub-agent pipeline for a single source_type. Returns a
    result dict; never raises — errors are captured in the "error" field so
    one failing agent can't take down the Supervisor's merge step."""
    db = SessionLocal()
    try:
        temp_request = db.get(TempRequest, temp_request_id)
        if temp_request is None:
            return {"source_type": source_type, "error": "temp_request not found"}

        # --- Planner: deterministic query formulation for this source ---
        query_text = f"{source_type.replace('_', ' ')} details: {user_text}" if user_text else source_type
        used_url = url
        discovered_via_search = False

        # --- Executor: fetch external content for this source ---
        existing_doc_for_source = db.execute(
            select(TempDocument).where(
                TempDocument.temp_request_id == temp_request.id,
                TempDocument.source_type == source_type,
            )
        ).scalars().first()

        if used_url is None and existing_doc_for_source is None and user_text:
            # No explicit URL and nothing fetched yet for this source — the
            # input dataset gives no URLs at all, so discover one via search.
            search_template = SEARCH_QUERY_TEMPLATES.get(source_type, "{query}")
            search_results = search_web(search_template.format(query=user_text), max_results=1)
            if search_results:
                used_url = search_results[0]["url"]
                discovered_via_search = True

        if used_url and existing_doc_for_source is None:
            already_fetched = db.execute(
                select(TempDocument).where(
                    TempDocument.temp_request_id == temp_request.id,
                    TempDocument.source_type == source_type,
                    TempDocument.external_url == used_url,
                )
            ).scalar_one_or_none()

            if already_fetched is None:
                fetch_result = call_source_agent(source_type, used_url)
                doc = TempDocument(
                    temp_request_id=temp_request.id,
                    source_type=source_type,
                    external_url=used_url,
                    extracted_text=fetch_result.get("text"),
                    extraction_status="success" if fetch_result.get("text") else "failed",
                    extraction_error=fetch_result.get("error"),
                )
                db.add(doc)
                db.commit()

            # Idempotent — safe even if other sub-agents already chunked
            # their own docs for this request.
            process_request_chunks_and_embeddings(db, temp_request)

        # --- Hybrid RAG: retrieve from this request's content + Main DB ---
        retrieved = hybrid_rag_retrieve(db, query_text, source_type, temp_request.id, top_k=5)

        # --- Normalize: extract the full candidate record from retrieved text ---
        request_texts = [r["text"] for r in retrieved if r["origin"] == "request"]
        combined_text = "\n\n".join(request_texts) if request_texts else "\n\n".join(r["text"] for r in retrieved)
        normalized = normalize_chunks(combined_text)

        # --- Validate: check normalized specs against Main DB values surfaced by Hybrid RAG ---
        conflicts = []
        main_db_product_ids = {r["product_id"] for r in retrieved if r["origin"] == "main_db" and r["product_id"]}
        if main_db_product_ids and normalized["specs"]:
            existing_attrs = (
                db.execute(select(ProductAttribute).where(ProductAttribute.product_id.in_(main_db_product_ids)))
                .scalars()
                .all()
            )
            existing_by_key: dict[str, list[str]] = {}
            for attr in existing_attrs:
                if attr.attribute_key:
                    existing_by_key.setdefault(attr.attribute_key.lower(), []).append(attr.attribute_value)

            for spec in normalized["specs"]:
                key = (spec.get("key") or "").lower()
                new_value = spec.get("value")
                for old_value in existing_by_key.get(key, []):
                    if old_value and new_value and old_value.strip().lower() != new_value.strip().lower():
                        conflicts.append({"key": key, "new_value": new_value, "existing_value": old_value})

        # --- Confidence Score: retrieval quality only (cross-agent agreement is the merge step's job) ---
        if retrieved:
            avg_score = sum(r["score"] for r in retrieved) / len(retrieved)
            confidence = round(100 / (1 + math.exp(-avg_score)))  # squash cross-encoder score to 0-100
        else:
            confidence = 0

        db.commit()
        return {
            "source_type": source_type,
            "query_text": query_text,
            "used_url": used_url,
            "discovered_via_search": discovered_via_search,
            "retrieved_count": len(retrieved),
            "retrieved_origins": [r["origin"] for r in retrieved],
            "title": normalized["title"],
            "manufacturer_name": normalized["manufacturer_name"],
            "specs": normalized["specs"],
            "features": normalized["features"],
            "dimensions": normalized["dimensions"],
            "identifiers": normalized["identifiers"],
            "warranty": normalized["warranty"],
            "price": normalized["price"],
            "country_of_origin": normalized["country_of_origin"],
            "category": normalized["category"],
            "conflicts": conflicts,
            "confidence": confidence,
            "error": None,
        }
    except Exception as e:
        db.rollback()
        return {"source_type": source_type, "error": str(e)}
    finally:
        db.close()

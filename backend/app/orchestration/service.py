from sqlalchemy.orm import Session

from app.delivery.merge import merge_agent_results
from app.delivery.schema import LONG_TAIL_COLUMNS
from app.models import TempDetectedProduct, TempProductAttribute, TempRequest
from app.orchestration.graph import graph_app

# Maps merged-record fields to their exact delivery column names (see
# app/delivery/schema.py). Only fields that land in the JSONB long tail —
# core fields (title, manufacturer_name) get real columns instead.
DIMENSION_FIELD_TO_COLUMN = {
    "length": "LENGTH", "length_uom": "LENGTH_UOM",
    "width": "WIDTH", "width_uom": "WIDTH_UOM",
    "height": "HEIGHT", "height_uom": "HEIGHT_UOM",
    "weight": "WEIGHT", "weight_uom": "WEIGHT_UOM",
}
IDENTIFIER_FIELD_TO_COLUMN = {"upc": "UPC", "ean": "EAN", "gtin": "GTIN", "unspsc": "UNSPSC"}
CATEGORY_FIELD_TO_COLUMN = {"dept": "Dept", "class": "Class", "fine": "Fine"}
URL_SOURCE_TO_COLUMN = {
    "website": "MFR URL",
    "catalog": "Ref URL 1",
    "tech_doc": "Specification Sheet",
    "digital_asset": "Product Image",
}


def _build_delivery_fields(merged: dict) -> dict:
    fields = {}
    if merged.get("warranty"):
        fields["Warranty"] = merged["warranty"]
    if merged.get("price"):
        fields["List Price"] = merged["price"]
    if merged.get("country_of_origin"):
        fields["Country Of Origin"] = merged["country_of_origin"]

    dimensions = merged.get("dimensions") or {}
    for field, column in DIMENSION_FIELD_TO_COLUMN.items():
        if dimensions.get(field):
            fields[column] = dimensions[field]

    identifiers = merged.get("identifiers") or {}
    for field, column in IDENTIFIER_FIELD_TO_COLUMN.items():
        if identifiers.get(field):
            fields[column] = identifiers[field]

    category = merged.get("category") or {}
    for field, column in CATEGORY_FIELD_TO_COLUMN.items():
        if category.get(field):
            fields[column] = category[field]

    for source_type, url in (merged.get("urls") or {}).items():
        column = URL_SOURCE_TO_COLUMN.get(source_type)
        if column and url:
            fields[column] = url

    # Anything not covered above stays blank — only known LONG_TAIL_COLUMNS
    # keys ever get written, so export never emits an unexpected column.
    return {k: v for k, v in fields.items() if k in LONG_TAIL_COLUMNS}


def orchestrate_request(db: Session, request_id: str, urls: dict | None = None, max_concurrency: int | None = None) -> dict:
    """max_concurrency bounds how many of this request's own sub-agents run
    at once (up to 4: website/catalog/tech_doc/digital_asset). Defaults to
    min(4, cores-2) for a single ad-hoc request. When called from the batch
    endpoint (many requests processed concurrently across a thread pool),
    pass max_concurrency=1 so each request's agents run serially — the outer
    batch pool is then the only source of parallelism, keeping total
    concurrent CPU-heavy work bounded at cores-2 instead of multiplying by 4."""
    temp_request = db.get(TempRequest, request_id)
    if temp_request is None:
        return {"error": "request_id not found"}

    initial_state = {
        "temp_request_id": request_id,
        "user_text": temp_request.user_text or "",
        "sources_selected": temp_request.sources_selected or [],
        "urls": urls or {},
        "guardrail_blocked": False,
        "guardrail_reason": None,
        "agent_results": {},
    }

    if max_concurrency is None:
        from app.concurrency import get_worker_count

        max_concurrency = min(4, get_worker_count())

    final_state = graph_app.invoke(initial_state, config={"max_concurrency": max_concurrency})

    if final_state.get("guardrail_blocked"):
        return {
            "request_id": request_id,
            "guardrail_blocked": True,
            "guardrail_reason": final_state.get("guardrail_reason"),
            "agent_results": {},
        }

    agent_results = final_state.get("agent_results", {})
    merged = merge_agent_results(agent_results)

    provenance = {
        source_type: {
            "used_url": r.get("used_url"),
            "discovered_via_search": r.get("discovered_via_search", False),
            "retrieved_count": r.get("retrieved_count", 0),
            "retrieved_origins": r.get("retrieved_origins", []),
            "confidence": r.get("confidence"),
            "conflicts": r.get("conflicts", []),
            "error": r.get("error"),
        }
        for source_type, r in agent_results.items()
    }

    detected = TempDetectedProduct(
        temp_request_id=temp_request.id,
        title=merged.get("title"),
        mfg_part_num=temp_request.mfg_part_num,
        part_desc=temp_request.part_desc,
        e1_brand=temp_request.e1_brand,
        unilog_brand=temp_request.unilog_brand,
        dib_brand=temp_request.dib_brand,
        part_manuf=temp_request.part_manuf,
        manufacturer_name=merged.get("manufacturer_name"),
        delivery_fields=_build_delivery_fields(merged),
        agent_provenance=provenance,
        status="draft",
    )
    db.add(detected)
    db.flush()

    conflicts_by_key: dict[str, list[dict]] = {}
    for c in merged.get("conflicts", []):
        conflicts_by_key.setdefault((c.get("key") or "").lower(), []).append(c)

    for spec in merged.get("specs", []):
        matching_conflicts = conflicts_by_key.get((spec.get("key") or "").lower(), [])
        db.add(
            TempProductAttribute(
                temp_detected_product_id=detected.id,
                attribute_type="spec",
                attribute_key=spec.get("key"),
                attribute_value=spec.get("value"),
                unit=spec.get("uom"),
                confidence=merged.get("overall_confidence"),
                extra={"conflicts": matching_conflicts} if matching_conflicts else None,
            )
        )

    for feature in merged.get("features", []):
        value = feature.get("value") if isinstance(feature, dict) else feature
        db.add(
            TempProductAttribute(
                temp_detected_product_id=detected.id,
                attribute_type="feature",
                attribute_value=value,
                confidence=merged.get("overall_confidence"),
            )
        )

    db.commit()

    return {
        "request_id": request_id,
        "guardrail_blocked": False,
        "detected_product_id": str(detected.id),
        "agent_results": agent_results,
        "merged": merged,
    }


def _orchestrate_one_with_own_session(request_id: str) -> dict:
    """Used by orchestrate_batch — each worker thread needs its own DB
    session (Session objects aren't thread-safe to share), and each request's
    own agents run serially (max_concurrency=1) since the batch pool itself
    is the parallelism source here — see orchestrate_request's docstring."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return orchestrate_request(db, request_id, urls={}, max_concurrency=1)
    except Exception as e:
        return {"request_id": request_id, "error": str(e)}
    finally:
        db.close()


def orchestrate_batch(request_ids: list[str]) -> dict:
    """Processes many requests concurrently — the real fix for the 1,000-row
    dataset use case, where running requests one at a time through the UI
    would take hours. Worker count follows the project's standing rule
    (cores - 2); each request's own up-to-4 agents run serially internally
    so total concurrent CPU-heavy work stays bounded at that same cores-2
    ceiling instead of multiplying by 4 per request."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from app.concurrency import get_worker_count

    if not request_ids:
        return {"processed": 0, "results": []}

    workers = min(get_worker_count(), len(request_ids))
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_id = {executor.submit(_orchestrate_one_with_own_session, rid): rid for rid in request_ids}
        for future in as_completed(future_to_id):
            request_id = future_to_id[future]
            try:
                results.append(future.result())
            except Exception as e:
                results.append({"request_id": request_id, "error": str(e)})

    return {"processed": len(results), "workers_used": workers, "results": results}

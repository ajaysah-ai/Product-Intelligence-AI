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


def orchestrate_request(db: Session, request_id: str, urls: dict | None = None) -> dict:
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

    final_state = graph_app.invoke(initial_state)

    if final_state.get("guardrail_blocked"):
        return {
            "request_id": request_id,
            "guardrail_blocked": True,
            "guardrail_reason": final_state.get("guardrail_reason"),
            "agent_results": {},
        }

    agent_results = final_state.get("agent_results", {})
    merged = merge_agent_results(agent_results)

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
        status="draft",
    )
    db.add(detected)
    db.flush()

    for spec in merged.get("specs", []):
        db.add(
            TempProductAttribute(
                temp_detected_product_id=detected.id,
                attribute_type="spec",
                attribute_key=spec.get("key"),
                attribute_value=spec.get("value"),
                unit=spec.get("uom"),
                confidence=merged.get("overall_confidence"),
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

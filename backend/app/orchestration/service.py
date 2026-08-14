from sqlalchemy.orm import Session

from app.models import TempDetectedProduct, TempProductAttribute, TempRequest
from app.orchestration.graph import graph_app


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

    best_title = next((r["title"] for r in agent_results.values() if r.get("title")), None)
    detected = TempDetectedProduct(temp_request_id=temp_request.id, title=best_title, status="draft")
    db.add(detected)
    db.flush()

    for source_type, result in agent_results.items():
        if result.get("error"):
            continue
        for spec in result.get("specs", []):
            db.add(
                TempProductAttribute(
                    temp_detected_product_id=detected.id,
                    attribute_type="spec",
                    attribute_key=spec.get("key"),
                    attribute_value=spec.get("value"),
                    confidence=result.get("confidence"),
                    extra={"source_type": source_type, "conflicts": result.get("conflicts", [])},
                )
            )
    db.commit()

    return {
        "request_id": request_id,
        "guardrail_blocked": False,
        "detected_product_id": str(detected.id),
        "agent_results": agent_results,
    }

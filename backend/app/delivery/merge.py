def _pick_highest_confidence(agent_results: dict, field: str):
    """Among agents that returned a non-null value for `field`, picks the
    value from whichever agent had the highest confidence score."""
    candidates = [
        (r.get("confidence", 0), r.get(field))
        for r in agent_results.values()
        if not r.get("error") and r.get(field)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def _merge_lists_dedup(agent_results: dict, field: str, key_field: str) -> list[dict]:
    """Unions a list-valued field (specs/features) across agents, deduping by
    key_field and keeping the highest-confidence version of each duplicate."""
    best_by_key: dict[str, tuple[float, dict]] = {}
    for result in agent_results.values():
        if result.get("error"):
            continue
        confidence = result.get("confidence", 0)
        for item in result.get(field, []) or []:
            if isinstance(item, str):
                dedup_key = item.strip().lower()
                item_dict = {"value": item}
            else:
                dedup_key = (item.get(key_field) or "").strip().lower()
                item_dict = item
            if not dedup_key:
                continue
            if dedup_key not in best_by_key or confidence > best_by_key[dedup_key][0]:
                best_by_key[dedup_key] = (confidence, item_dict)
    return [v[1] for v in best_by_key.values()]


def _collect_conflicts(agent_results: dict) -> list[dict]:
    """Every agent's Validate-step conflicts, tagged with which source found
    them — dropped by mistake in an earlier rewrite; restored here so
    Validation (per the requirements doc's Creation/Enrichment/Validation
    trio) is actually visible in the final output, not just inside each
    agent's raw result."""
    conflicts = []
    for source_type, result in agent_results.items():
        if result.get("error"):
            continue
        for c in result.get("conflicts", []) or []:
            conflicts.append({"source_type": source_type, **c})
    return conflicts


def merge_agent_results(agent_results: dict) -> dict:
    """Combines all sub-agents' results into one candidate record, picking
    the highest-confidence value per scalar field and deduping list fields
    (specs/features) across sources."""
    merged = {
        "title": _pick_highest_confidence(agent_results, "title"),
        "manufacturer_name": _pick_highest_confidence(agent_results, "manufacturer_name"),
        "warranty": _pick_highest_confidence(agent_results, "warranty"),
        "price": _pick_highest_confidence(agent_results, "price"),
        "country_of_origin": _pick_highest_confidence(agent_results, "country_of_origin"),
        "dimensions": _pick_highest_confidence(agent_results, "dimensions"),
        "identifiers": _pick_highest_confidence(agent_results, "identifiers"),
        "category": _pick_highest_confidence(agent_results, "category"),
        "specs": _merge_lists_dedup(agent_results, "specs", "key"),
        "features": _merge_lists_dedup(agent_results, "features", "value"),
        "conflicts": _collect_conflicts(agent_results),
        "urls": {
            source_type: r["used_url"]
            for source_type, r in agent_results.items()
            if not r.get("error") and r.get("used_url")
        },
        "overall_confidence": round(
            sum(r.get("confidence", 0) for r in agent_results.values() if not r.get("error"))
            / max(1, sum(1 for r in agent_results.values() if not r.get("error")))
        )
        if agent_results
        else 0,
    }
    return merged

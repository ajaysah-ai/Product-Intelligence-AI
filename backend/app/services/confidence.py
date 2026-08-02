"""
Confidence scoring (SYSTEM_DESIGN.md 1.5)

confidence = (source_agreement * 0.5) + (source_reliability * 0.3) + (completeness * 0.2)

This is the starting-point formula from the design doc. Weights are
tunable constants below — adjust after testing against your sample set.
"""

AGREEMENT_WEIGHT = 0.5
RELIABILITY_WEIGHT = 0.3
COMPLETENESS_WEIGHT = 0.2

REVIEW_THRESHOLD = 60  # fields below this confidence trigger human-in-the-loop


def field_confidence(
    source_agreement: float,
    source_reliability: float,
    data_completeness: float,
) -> float:
    """All three inputs are 0-100. Returns a 0-100 confidence score."""
    score = (
        source_agreement * AGREEMENT_WEIGHT
        + source_reliability * RELIABILITY_WEIGHT
        + data_completeness * COMPLETENESS_WEIGHT
    )
    return round(min(max(score, 0), 100), 2)


def rollup_confidence(field_scores: list[float]) -> float | None:
    """Simple average rollup for products.overall_confidence.
    Swap for a weighted average (e.g. weight specs higher than warranty)
    once you know which fields matter most for the demo."""
    valid = [s for s in field_scores if s is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


def needs_review(field_scores: dict[str, float]) -> list[str]:
    return [field for field, score in field_scores.items() if score is not None and score < REVIEW_THRESHOLD]

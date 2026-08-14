import re

# Pattern-level detection, not an exhaustive blocklist — catches the common
# shapes of injection attempts (instruction override, role hijack, data
# exfiltration requests) without needing an LLM call on every request.
SUSPICIOUS_PATTERNS = [
    r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b",
    r"\bdisregard\s+(the\s+)?(system\s+)?prompt\b",
    r"\breveal\s+(your\s+)?(system\s+)?(prompt|instructions)\b",
    r"\byou\s+are\s+now\s+(in\s+)?(developer|debug|admin)\s+mode\b",
    r"\bact\s+as\s+(if\s+you\s+(have|are)|an?\s+unrestricted)\b",
    r"\bjailbreak\b",
    r"\bbypass\s+(your\s+)?(safety|restrictions?|guardrails?)\b",
    r"\boutput\s+(the\s+)?raw\s+(db|database)\b",
    r"\bdrop\s+table\b",
    r"\bdelete\s+from\s+\w+\b",
    r"\bshow\s+me\s+(all\s+)?(rows|records|the\s+database)\b",
    r"\bsystem\s*:\s*",  # attempts to inject a fake role marker
    r"\bpretend\s+you\s+are\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SUSPICIOUS_PATTERNS]

# Two or more independent matches is a much stronger signal than one phrase
# that happens to overlap a pattern in ordinary product-description text.
BLOCK_THRESHOLD = 2


def check_prompt_injection(text: str) -> dict:
    """Returns {"blocked": bool, "reason": str|None, "matched_patterns": [...]}."""
    if not text:
        return {"blocked": False, "reason": None, "matched_patterns": []}

    matches = [p.pattern for p in _COMPILED_PATTERNS if p.search(text)]

    if len(matches) >= BLOCK_THRESHOLD:
        return {
            "blocked": True,
            "reason": f"Detected {len(matches)} suspicious instruction-override patterns in input text.",
            "matched_patterns": matches,
        }

    return {"blocked": False, "reason": None, "matched_patterns": matches}

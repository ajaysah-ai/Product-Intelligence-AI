import json
import os
import re

_llm = None
_llm_init_attempted = False


def _get_llm():
    """Lazy singleton. Returns None (not an exception) if GROQ_API_KEY isn't
    set — callers fall back to heuristic extraction rather than failing the
    whole request over a missing key."""
    global _llm, _llm_init_attempted
    if _llm_init_attempted:
        return _llm
    _llm_init_attempted = True

    if not os.getenv("GROQ_API_KEY"):
        return None

    from langchain_groq import ChatGroq

    _llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        temperature=0,
    )
    return _llm


NORMALIZE_PROMPT = """You extract structured product information from source text.
Given the text below, identify:
1. A short product title (best guess, or null if unclear)
2. Up to 3 specs as key/value pairs (e.g. "power": "750W", "battery_life": "40 hours")

Respond with ONLY valid JSON, no markdown fences, no explanation, in this exact shape:
{{"title": "..." or null, "specs": [{{"key": "...", "value": "..."}}]}}

Source text:
---
{text}
---"""


def _heuristic_normalize(text: str) -> dict:
    """Fallback used when no LLM is configured. Regex-based: grabs the first
    sentence as a title candidate and any "NUMBER unit" patterns as specs.
    Intentionally simple — real extraction quality comes from the LLM path;
    this just keeps the pipeline runnable without an API key."""
    first_sentence = re.split(r"(?<=[.!?])\s", text.strip())[0][:120] if text.strip() else None

    spec_pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*(W|hours?|hrs?|GB|MB|mm|cm|kg|g|V|mAh)\b", re.IGNORECASE)
    specs = []
    seen_units = set()
    for match in spec_pattern.finditer(text):
        unit = match.group(2).lower()
        if unit in seen_units:
            continue
        seen_units.add(unit)
        specs.append({"key": unit, "value": f"{match.group(1)}{match.group(2)}"})
        if len(specs) >= 3:
            break

    return {"title": first_sentence, "specs": specs}


def normalize_chunks(chunks_text: str) -> dict:
    """Returns {"title": str|None, "specs": [{"key","value"}]}. Uses the LLM
    when GROQ_API_KEY is configured, otherwise falls back to heuristics."""
    if not chunks_text or not chunks_text.strip():
        return {"title": None, "specs": []}

    llm = _get_llm()
    if llm is None:
        return _heuristic_normalize(chunks_text)

    try:
        response = llm.invoke(NORMALIZE_PROMPT.format(text=chunks_text[:4000]))
        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or "specs" not in parsed:
            raise ValueError("Unexpected LLM response shape")
        return {"title": parsed.get("title"), "specs": parsed.get("specs", [])}
    except Exception:
        # LLM call failed or returned unparseable output — don't fail the
        # whole sub-agent over it, degrade to the heuristic path.
        return _heuristic_normalize(chunks_text)

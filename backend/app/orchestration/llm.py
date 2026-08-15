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


NORMALIZE_PROMPT = """You extract structured product catalog information from source text.
Given the text below, extract as much as you can find (use null/empty for anything not present):

- title: short product title
- manufacturer_name: the manufacturer's name
- specs: up to 10 {{"key","value","uom"}} objects for technical specifications (uom = unit of measure, or null)
- features: up to 10 short feature description strings
- dimensions: {{"length","length_uom","width","width_uom","height","height_uom","weight","weight_uom"}} — numbers as strings, or null
- identifiers: {{"upc","ean","gtin","unspsc"}} — or null
- warranty: warranty text, or null
- price: price as a string (e.g. "49.99"), or null
- country_of_origin: country name, or null
- category: {{"dept","class","fine"}} — a 3-level product category guess (e.g. dept="Appliances", class="Dishwashers", fine="Built-In"), or null

Respond with ONLY valid JSON, no markdown fences, no explanation, in this exact shape:
{{"title": null, "manufacturer_name": null, "specs": [], "features": [], "dimensions": null, "identifiers": null, "warranty": null, "price": null, "country_of_origin": null, "category": null}}

Source text:
---
{text}
---"""


def _empty_result() -> dict:
    return {
        "title": None,
        "manufacturer_name": None,
        "specs": [],
        "features": [],
        "dimensions": None,
        "identifiers": None,
        "warranty": None,
        "price": None,
        "country_of_origin": None,
        "category": None,
    }


def _heuristic_normalize(text: str) -> dict:
    """Fallback used when no LLM is configured. Regex-based — grabs the first
    sentence as a title candidate, "NUMBER unit" patterns as specs, and a few
    identifier/price patterns. Intentionally simple; real extraction quality
    comes from the LLM path once GROQ_API_KEY is set."""
    result = _empty_result()
    if not text or not text.strip():
        return result

    result["title"] = re.split(r"(?<=[.!?])\s", text.strip())[0][:120]

    spec_pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*(W|hours?|hrs?|GB|MB|mm|cm|kg|g|V|mAh)\b", re.IGNORECASE)
    seen_units = set()
    for match in spec_pattern.finditer(text):
        unit = match.group(2).lower()
        if unit in seen_units:
            continue
        seen_units.add(unit)
        result["specs"].append({"key": unit, "value": f"{match.group(1)}{match.group(2)}", "uom": match.group(2)})
        if len(result["specs"]) >= 5:
            break

    price_match = re.search(r"\$\s?(\d+(?:\.\d{2})?)", text)
    if price_match:
        result["price"] = price_match.group(1)

    upc_match = re.search(r"\b(\d{12})\b", text)
    if upc_match:
        result["identifiers"] = {"upc": upc_match.group(1), "ean": None, "gtin": None, "unspsc": None}

    return result


def normalize_chunks(chunks_text: str) -> dict:
    """Returns the full extraction shape (see _empty_result). Uses the LLM
    when GROQ_API_KEY is configured, otherwise falls back to heuristics."""
    if not chunks_text or not chunks_text.strip():
        return _empty_result()

    llm = _get_llm()
    if llm is None:
        return _heuristic_normalize(chunks_text)

    try:
        response = llm.invoke(NORMALIZE_PROMPT.format(text=chunks_text[:6000]))
        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Unexpected LLM response shape")
        result = _empty_result()
        result.update({k: v for k, v in parsed.items() if k in result})
        return result
    except Exception:
        # LLM call failed or returned unparseable output — don't fail the
        # whole sub-agent over it, degrade to the heuristic path.
        return _heuristic_normalize(chunks_text)

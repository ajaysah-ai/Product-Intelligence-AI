"""
Prompt templates for the Enrichment Agent.

Design rules (see SYSTEM_DESIGN.md Part 2):
1. Ground strictly in provided context — never fall back to general knowledge.
2. One field-group per call, not one giant call.
3. Require source_document_id citation on every extracted item.
4. JSON-only output, enforced via chat_completion_json / response_format.
"""

SYSTEM_PROMPT = """You are a product data extraction engine. You extract structured \
product information ONLY from the context chunks provided to you. \
Rules:
- Never use outside/general knowledge. If a value is not present in the context, \
  set it to null rather than guessing.
- Every extracted item MUST include the source_document_id of the chunk it came from.
- Return valid JSON only — no prose, no markdown fences, no explanation.
- Assign a confidence (0-100) to each item based on how directly and unambiguously \
  the context supports it.
"""


def build_context_block(chunks: list[dict]) -> str:
    """chunks: list of {source_document_id, chunk_text} dicts from the Retrieval Agent."""
    parts = []
    for c in chunks:
        parts.append(f"[source_document_id: {c['source_document_id']}]\n{c['chunk_text']}")
    return "\n\n---\n\n".join(parts)


def specs_prompt(product_identity: dict, chunks: list[dict]) -> list[dict]:
    context = build_context_block(chunks)
    user_prompt = f"""Product: {product_identity.get('brand')} {product_identity.get('part_number')} \
({product_identity.get('description', '')})

Context:
{context}

Extract all technical specifications (power, voltage, disc diameter, no-load speed, \
weight, frequency, and any others present). Return JSON:
{{"specs": [{{"spec_name": str, "spec_value": str, "spec_unit": str, "confidence": int, \
"source_document_id": str}}]}}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def features_prompt(product_identity: dict, chunks: list[dict]) -> list[dict]:
    context = build_context_block(chunks)
    user_prompt = f"""Product: {product_identity.get('brand')} {product_identity.get('part_number')}

Context:
{context}

Extract features that make this product useful (short bullet-style phrases). Return JSON:
{{"features": [{{"feature_text": str, "confidence": int, "source_document_id": str}}]}}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def dimensions_prompt(product_identity: dict, chunks: list[dict]) -> list[dict]:
    context = build_context_block(chunks)
    user_prompt = f"""Product: {product_identity.get('brand')} {product_identity.get('part_number')}

Context:
{context}

Extract physical dimensions in millimeters and weight in kilograms. Return JSON:
{{"dimensions": {{"length_mm": number, "width_mm": number, "height_mm": number, \
"weight_kg": number, "confidence": int, "source_document_id": str}}}}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def materials_prompt(product_identity: dict, chunks: list[dict]) -> list[dict]:
    context = build_context_block(chunks)
    user_prompt = f"""Product: {product_identity.get('brand')} {product_identity.get('part_number')}

Context:
{context}

Extract what each component is made of (e.g. housing, gear, guard, handle). Return JSON:
{{"materials": [{{"component": str, "material": str, "source_document_id": str}}]}}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def applications_prompt(product_identity: dict, chunks: list[dict]) -> list[dict]:
    context = build_context_block(chunks)
    user_prompt = f"""Product: {product_identity.get('brand')} {product_identity.get('part_number')}

Context:
{context}

Extract where/how this product is used. Return JSON:
{{"applications": [{{"application_text": str, "source_document_id": str}}]}}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def warranty_prompt(product_identity: dict, chunks: list[dict]) -> list[dict]:
    context = build_context_block(chunks)
    user_prompt = f"""Product: {product_identity.get('brand')} {product_identity.get('part_number')}

Context:
{context}

Extract warranty details. Return JSON:
{{"warranty": {{"duration_text": str, "registration_required": bool, "confidence": int, \
"source_document_id": str}}}}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def title_prompt(product_identity: dict, chunks: list[dict]) -> list[dict]:
    context = build_context_block(chunks)
    user_prompt = f"""Product: {product_identity.get('brand')} {product_identity.get('part_number')} \
({product_identity.get('description', '')})

Context:
{context}

Generate a product title in the format: Brand Model Power ProductType (Size). \
Example: "Bosch GWS 750-100 Professional 750W Angle Grinder (100mm)". Return JSON:
{{"title": str}}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]

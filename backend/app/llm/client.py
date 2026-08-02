"""
Thin wrapper around Groq's OpenAI-compatible chat completions endpoint.

Groq serves openai/gpt-oss-120b at an OpenAI-compatible /chat/completions
route, so we reuse the `openai` SDK pointed at Groq's base_url. OmniRoute
is wired the same way as a swappable alternate provider — set
OMNIROUTE_BASE_URL / OMNIROUTE_API_KEY and pass provider="omniroute".

Note: Groq does not serve an embeddings endpoint. Embeddings are handled
separately in app/llm/embeddings.py via a local sentence-transformers model.
"""

import json

from openai import AsyncOpenAI

from app.config import settings

_groq_client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)

_omniroute_client: AsyncOpenAI | None = None
if settings.omniroute_api_key and settings.omniroute_base_url:
    _omniroute_client = AsyncOpenAI(api_key=settings.omniroute_api_key, base_url=settings.omniroute_base_url)


def _client_for(provider: str) -> AsyncOpenAI:
    if provider == "omniroute":
        if _omniroute_client is None:
            raise RuntimeError("OmniRoute not configured — set OMNIROUTE_API_KEY and OMNIROUTE_BASE_URL")
        return _omniroute_client
    return _groq_client


async def chat_completion(
    messages: list[dict],
    provider: str = "groq",
    model: str | None = None,
    temperature: float = 0.1,
    json_mode: bool = False,
) -> str:
    """Run a single chat completion. Returns the raw text content.

    json_mode=True asks the model to return valid JSON only — use this
    for every Enrichment Agent call, per the extraction JSON contract.
    """
    client = _client_for(provider)
    kwargs = {
        "model": model or settings.groq_model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def chat_completion_json(messages: list[dict], provider: str = "groq", model: str | None = None) -> dict:
    """Run a chat completion and parse the result as JSON.

    Raises ValueError if the model didn't return valid JSON — callers
    (e.g. the Enrichment Agent) should catch this and retry once per
    the "structured output enforcement" prompt rule.
    """
    raw = await chat_completion(messages, provider=provider, model=model, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {raw[:200]}") from exc

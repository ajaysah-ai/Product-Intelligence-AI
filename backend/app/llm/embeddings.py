"""
Local embedding model for document_chunks.embedding (pgvector).

Groq does not serve an embeddings endpoint, so we run a small local
sentence-transformers model instead — free, no external API call per
chunk, and dimension-stable (384) to match the schema. The model is
loaded once at import time and reused across requests.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def embed_text(text: str) -> list[float]:
    """Embed a single string. Returns a list[float] of length settings.embedding_dim."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings in one batch call — use this for chunking a
    whole document instead of calling embed_text() in a loop."""
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vectors]

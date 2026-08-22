import os

_model = None


def _get_model():
    """Loads the model once and reuses it — SentenceTransformer construction
    is expensive (model load + tokenizer), so this must not run per-call.
    Uses GPU automatically if one's available."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        from app.concurrency import get_device

        model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        _model = SentenceTransformer(model_name, device=get_device())
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embeds a list of texts in a single model forward pass — always
    prefer calling this once with many texts over calling it once per text."""
    if not texts:
        return []

    from app.models import EMBEDDING_DIM

    model = _get_model()
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True)
    vectors_list = vectors.tolist()

    if vectors_list and len(vectors_list[0]) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch: model produced {len(vectors_list[0])}-dim "
            f"vectors but the schema expects {EMBEDDING_DIM}. Check EMBEDDING_MODEL_NAME "
            f"and EMBEDDING_DIM in .env."
        )

    return vectors_list

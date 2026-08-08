import os

DEFAULT_CHUNK_SIZE_WORDS = int(os.getenv("CHUNK_SIZE_WORDS", "500"))
DEFAULT_CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "50"))


def chunk_text(text: str, chunk_size_words: int = None, overlap_words: int = None) -> list[str]:
    """Splits text into overlapping word-count chunks. Deterministic and
    dependency-free — no tokenizer needed, which keeps this fast even on
    very large extracted documents."""
    chunk_size_words = chunk_size_words if chunk_size_words is not None else DEFAULT_CHUNK_SIZE_WORDS
    overlap_words = overlap_words if overlap_words is not None else DEFAULT_CHUNK_OVERLAP_WORDS

    if chunk_size_words <= 0:
        raise ValueError("chunk_size_words must be positive")
    if overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be smaller than chunk_size_words")

    words = text.split()
    if not words:
        return []

    step = chunk_size_words - overlap_words
    chunks = []
    start = 0
    while start < len(words):
        chunk_words = words[start : start + chunk_size_words]
        chunks.append(" ".join(chunk_words))
        if start + chunk_size_words >= len(words):
            break
        start += step

    return chunks

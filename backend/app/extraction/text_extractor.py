from app.extraction.errors import ExtractionError


def extract_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        raise ExtractionError(f"TXT extraction failed: {e}") from e

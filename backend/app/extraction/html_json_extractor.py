import json as json_lib

from bs4 import BeautifulSoup

from app.extraction.errors import ExtractionError


def extract_html(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        return soup.get_text(separator="\n")
    except Exception as e:
        raise ExtractionError(f"HTML extraction failed: {e}") from e


def extract_json(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json_lib.load(f)
        return json_lib.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        raise ExtractionError(f"JSON extraction failed: {e}") from e

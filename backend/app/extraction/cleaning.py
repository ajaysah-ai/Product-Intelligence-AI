import re
import unicodedata


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)

    # Strip control characters but keep newline/tab
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)

    # Collapse excess blank lines and repeated spaces/tabs
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()

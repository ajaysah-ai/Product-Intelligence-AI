import io

import numpy as np
from PIL import Image

from app.extraction.errors import ExtractionError

_reader = None


def _get_reader():
    """EasyOCR downloads model weights on first use and takes a few seconds to
    initialize — loading it once and reusing it across files/requests matters
    a lot for batch throughput."""
    global _reader
    if _reader is None:
        import easyocr  # deferred import: keeps startup fast when no image is being processed

        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def extract_image(path: str) -> str:
    """OCR for a standalone image file (a user-uploaded .png/.jpg)."""
    try:
        reader = _get_reader()
        results = reader.readtext(path, detail=0)
        return "\n".join(results)
    except Exception as e:
        raise ExtractionError(f"Image OCR failed: {e}") from e


def extract_image_from_bytes(image_bytes: bytes) -> str:
    """OCR for an image that lives inside another document (a PDF's embedded
    figure, a DOCX's inline picture, or a rasterized scanned page) — no need
    to write it to disk first."""
    try:
        reader = _get_reader()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        results = reader.readtext(arr, detail=0)
        return "\n".join(results)
    except Exception as e:
        raise ExtractionError(f"Embedded image OCR failed: {e}") from e

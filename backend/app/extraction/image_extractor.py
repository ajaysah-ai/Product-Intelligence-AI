import io

import numpy as np
from PIL import Image

from app.extraction.errors import ExtractionError

_reader = None


def _get_reader():
    """EasyOCR downloads model weights on first use and takes a few seconds to
    initialize — loading it once and reusing it across files/requests matters
    a lot for batch throughput. Uses GPU automatically if one's available."""
    global _reader
    if _reader is None:
        import easyocr  # deferred import: keeps startup fast when no image is being processed

        from app.concurrency import get_device

        _reader = easyocr.Reader(["en"], gpu=(get_device() == "cuda"))
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


def extract_images_concurrently(image_byte_list: list[bytes]) -> list[str]:
    """OCRs multiple images from the same document in parallel instead of one
    at a time — bounded by the project's worker-count rule (cores - 2). Used
    by the PDF/DOCX extractors, which collect all their OCR-eligible images
    up front and hand them here as one batch. One failing image doesn't drop
    the others."""
    if not image_byte_list:
        return []

    from concurrent.futures import ThreadPoolExecutor

    from app.concurrency import get_worker_count

    workers = min(get_worker_count(), len(image_byte_list))
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submission order (not as_completed) so output stays in the same
        # order the images were found in the document — total wall time is
        # still bounded by the pool regardless of how we collect results.
        futures = [executor.submit(extract_image_from_bytes, b) for b in image_byte_list]
        for future in futures:
            try:
                text = future.result()
                if text.strip():
                    results.append(text)
            except ExtractionError:
                continue  # one bad image shouldn't drop the rest
    return results

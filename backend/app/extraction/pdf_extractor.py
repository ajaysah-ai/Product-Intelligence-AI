import fitz  # PyMuPDF

from app.extraction.errors import ExtractionError
from app.extraction.image_extractor import extract_image_from_bytes

# Skip tiny embedded images (icons, bullets, logos) — OCR-ing them wastes time
# and mostly produces noise, not useful product text.
MIN_IMAGE_BYTES = 2000


def extract_pdf(path: str) -> str:
    try:
        doc = fitz.open(path)
        try:
            parts = []
            for page in doc:
                page_text = page.get_text()

                if page_text.strip():
                    parts.append(page_text)
                else:
                    # No text layer at all on this page -> likely a scanned page.
                    # Rasterize it and OCR the whole thing as a fallback.
                    pix = page.get_pixmap(dpi=200)
                    try:
                        ocr_text = extract_image_from_bytes(pix.tobytes("png"))
                        if ocr_text.strip():
                            parts.append(ocr_text)
                    except ExtractionError:
                        pass  # one bad page shouldn't fail the whole document

                # Also OCR embedded images (diagrams, product photos) even on
                # pages that DO have a text layer — a spec sheet often has both.
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        if len(image_bytes) < MIN_IMAGE_BYTES:
                            continue
                        ocr_text = extract_image_from_bytes(image_bytes)
                        if ocr_text.strip():
                            parts.append(ocr_text)
                    except Exception:
                        continue  # one bad embedded image shouldn't fail the page
        finally:
            doc.close()
        return "\n".join(parts)
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"PDF extraction failed: {e}") from e

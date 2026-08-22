import fitz  # PyMuPDF

from app.extraction.errors import ExtractionError
from app.extraction.image_extractor import extract_images_concurrently

# Skip tiny embedded images (icons, bullets, logos) — OCR-ing them wastes time
# and mostly produces noise, not useful product text.
MIN_IMAGE_BYTES = 2000

# Hard cap on OCR calls per document — EasyOCR is genuinely slow per image,
# and a real spec-sheet PDF can have a dozen embedded images. Images are
# collected up front and OCR'd concurrently (see extract_images_concurrently),
# but the cap still bounds worst-case work regardless of parallelism.
MAX_IMAGES_OCR_PER_DOC = 5


def extract_pdf(path: str) -> str:
    try:
        doc = fitz.open(path)
        try:
            text_parts = []
            ocr_tasks: list[bytes] = []  # collected up front, OCR'd concurrently after the loop

            for page in doc:
                page_text = page.get_text()

                if page_text.strip():
                    text_parts.append(page_text)
                elif len(ocr_tasks) < MAX_IMAGES_OCR_PER_DOC:
                    # No text layer at all on this page -> likely a scanned page.
                    # Rasterize it; OCR happens in the concurrent batch below.
                    pix = page.get_pixmap(dpi=200)
                    ocr_tasks.append(pix.tobytes("png"))

                # Also queue embedded images (diagrams, product photos) even on
                # pages that DO have a text layer — a spec sheet often has both.
                for img_info in page.get_images(full=True):
                    if len(ocr_tasks) >= MAX_IMAGES_OCR_PER_DOC:
                        break
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        if len(image_bytes) < MIN_IMAGE_BYTES:
                            continue
                        ocr_tasks.append(image_bytes)
                    except Exception:
                        continue  # one bad embedded image shouldn't fail the page
        finally:
            doc.close()

        ocr_parts = extract_images_concurrently(ocr_tasks)
        return "\n".join(text_parts + ocr_parts)
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"PDF extraction failed: {e}") from e

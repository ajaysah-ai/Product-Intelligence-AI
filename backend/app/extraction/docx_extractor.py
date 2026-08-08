from docx import Document as DocxDocument

from app.extraction.errors import ExtractionError
from app.extraction.image_extractor import extract_image_from_bytes

MIN_IMAGE_BYTES = 2000  # skip tiny icons/logos — same reasoning as the PDF extractor


def extract_docx(path: str) -> str:
    try:
        d = DocxDocument(path)
        parts = [p.text for p in d.paragraphs if p.text.strip()]

        for table in d.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        # Embedded pictures live as relationship parts (word/media/*) — python-docx
        # doesn't surface these through the paragraph API, so we go via .part.rels.
        for rel in d.part.rels.values():
            if "image" in rel.reltype:
                try:
                    image_bytes = rel.target_part.blob
                    if len(image_bytes) < MIN_IMAGE_BYTES:
                        continue
                    ocr_text = extract_image_from_bytes(image_bytes)
                    if ocr_text.strip():
                        parts.append(ocr_text)
                except Exception:
                    continue  # one bad embedded image shouldn't fail the document

        return "\n".join(parts)
    except Exception as e:
        raise ExtractionError(f"DOCX extraction failed: {e}") from e

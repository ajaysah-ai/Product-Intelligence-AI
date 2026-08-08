from pathlib import Path

from app.extraction.cleaning import clean_text
from app.extraction.docx_extractor import extract_docx
from app.extraction.errors import ExtractionError
from app.extraction.html_json_extractor import extract_html, extract_json
from app.extraction.image_extractor import extract_image
from app.extraction.pdf_extractor import extract_pdf
from app.extraction.tabular_extractor import extract_csv, extract_xlsx
from app.extraction.text_extractor import extract_txt

EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".txt": extract_txt,
    ".csv": extract_csv,
    ".xlsx": extract_xlsx,
    ".html": extract_html,
    ".htm": extract_html,
    ".json": extract_json,
    ".png": extract_image,
    ".jpg": extract_image,
    ".jpeg": extract_image,
}


def extract_file(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        raise ExtractionError(f"No extractor registered for extension '{ext}'")

    raw_text = extractor(file_path)
    return clean_text(raw_text)

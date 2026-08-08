import csv

import openpyxl

from app.extraction.errors import ExtractionError


def extract_csv(path: str) -> str:
    """Streams row-by-row via stdlib csv.reader instead of pandas.read_csv().
    A full DataFrame load typically costs 3-5x the raw file size in memory;
    streaming keeps peak memory close to O(row size), which matters at the
    ~1M-row scale this pipeline needs to handle."""
    try:
        lines = []
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if any(cell.strip() for cell in row):
                    lines.append(" | ".join(row))
        return "\n".join(lines)
    except Exception as e:
        raise ExtractionError(f"CSV extraction failed: {e}") from e


def extract_xlsx(path: str) -> str:
    """openpyxl's read_only mode streams rows from the underlying XML instead
    of materializing the whole workbook, so large sheets don't blow up memory."""
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            parts = []
            for sheet in wb.worksheets:
                parts.append(f"[Sheet: {sheet.title}]")
                for row in sheet.iter_rows(values_only=True):
                    line = " | ".join("" if v is None else str(v) for v in row)
                    if line.strip(" |"):
                        parts.append(line)
        finally:
            wb.close()
        return "\n".join(parts)
    except Exception as e:
        raise ExtractionError(f"XLSX extraction failed: {e}") from e

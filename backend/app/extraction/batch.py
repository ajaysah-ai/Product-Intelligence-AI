import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.extraction.dispatcher import extract_file
from app.extraction.errors import ExtractionError


def _worker_count() -> int:
    cpu = os.cpu_count() or 2
    return max(1, cpu - 2)


def extract_batch(file_paths: list[str]) -> dict[str, dict]:
    """Extracts multiple files concurrently. One failing file never takes down
    the others — each result is tagged success/failed independently.
    Returns {file_path: {"status": "success"|"failed", "text": str|None, "error": str|None}}
    """
    results: dict[str, dict] = {}
    if not file_paths:
        return results

    workers = min(_worker_count(), len(file_paths))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_path = {executor.submit(extract_file, p): p for p in file_paths}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                text = future.result()
                results[path] = {"status": "success", "text": text, "error": None}
            except ExtractionError as e:
                results[path] = {"status": "failed", "text": None, "error": str(e)}
            except Exception as e:
                results[path] = {"status": "failed", "text": None, "error": f"Unexpected error: {e}"}

    return results

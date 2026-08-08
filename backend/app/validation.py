from pathlib import Path

import filetype
from fastapi import HTTPException, UploadFile

from app.config import (
    ALLOWED_EXTENSIONS,
    EXPECTED_SIGNATURE_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_REQUEST,
)


def validate_text_and_files(text: str | None, files: list[UploadFile]) -> None:
    """At least one of text or files must be present."""
    has_text = bool(text and text.strip())
    has_files = bool(files) and any(f.filename for f in files)
    if not has_text and not has_files:
        raise HTTPException(status_code=400, detail="Provide text, at least one file, or both.")

    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files: {len(files)} submitted, max is {MAX_FILES_PER_REQUEST}.",
        )


def validate_single_file(filename: str, content: bytes) -> str:
    """
    Validates one file's extension, size, and actual content signature.
    Returns the lowercased extension on success. Raises HTTPException on failure.
    """
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext or '(none)'}' is not allowed for '{filename}'.",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail=f"File '{filename}' is empty.")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File '{filename}' exceeds the {MAX_FILE_SIZE_BYTES // (1024*1024)}MB limit.",
        )

    category = ALLOWED_EXTENSIONS[ext]

    if category == "binary":
        guess = filetype.guess(content)
        detected = guess.extension if guess else None
        expected = EXPECTED_SIGNATURE_EXTENSIONS.get(ext, set())
        if detected not in expected:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File '{filename}' claims to be {ext} but its content signature "
                    f"looks like '{detected or 'unknown'}', not {sorted(expected)}."
                ),
            )
    else:
        # Text category: confirm it actually decodes as text (catches a renamed binary).
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{filename}' claims to be {ext} but isn't readable text.",
                )

    return ext

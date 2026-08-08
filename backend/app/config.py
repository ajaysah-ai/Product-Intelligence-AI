import os
from pathlib import Path

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/app/media"))

MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

MAX_FILES_PER_REQUEST = int(os.getenv("MAX_FILES_PER_REQUEST", "10"))

# Extension -> (category, filetype-library signature check needed?)
# "binary" extensions get their magic bytes verified against the claimed type.
# "text" extensions can't be magic-byte-sniffed reliably, so we just confirm
# the content decodes as text at all (catches renamed binaries).
ALLOWED_EXTENSIONS = {
    ".pdf": "binary",
    ".docx": "binary",
    ".xlsx": "binary",
    ".png": "binary",
    ".jpg": "binary",
    ".jpeg": "binary",
    ".txt": "text",
    ".csv": "text",
    ".html": "text",
    ".htm": "text",
    ".json": "text",
}

# filetype library's guessed extension for each of our "binary" extensions.
# docx/xlsx are zip-based; filetype reports them as "zip" at the container level,
# so we accept zip for those two and rely on extension + later Phase 3 parsing
# to catch anything that isn't actually a valid docx/xlsx.
EXPECTED_SIGNATURE_EXTENSIONS = {
    ".pdf": {"pdf"},
    ".docx": {"zip"},
    ".xlsx": {"zip"},
    ".png": {"png"},
    ".jpg": {"jpg", "jpeg"},
    ".jpeg": {"jpg", "jpeg"},
}

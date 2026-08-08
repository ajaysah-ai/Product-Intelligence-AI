class ExtractionError(Exception):
    """Raised when a single file can't be extracted. Callers catch this per-file
    so one bad file in a multi-file batch doesn't take down the others."""

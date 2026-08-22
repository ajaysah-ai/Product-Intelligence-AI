import os

_device = None


def get_worker_count() -> int:
    """Standing project rule: always leave 2 cores for the OS. Every thread
    pool in this codebase should size itself from this function, not
    duplicate the arithmetic."""
    cpu = os.cpu_count() or 4
    return max(1, cpu - 2)


def get_device() -> str:
    """Returns 'cuda' if a GPU is available, otherwise 'cpu'. Cached after
    first check — torch.cuda.is_available() does real device enumeration
    work, no need to repeat it on every model load."""
    global _device
    if _device is None:
        try:
            import torch

            _device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            _device = "cpu"
    return _device

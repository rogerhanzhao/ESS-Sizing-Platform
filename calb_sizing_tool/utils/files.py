from __future__ import annotations

import re
from pathlib import Path


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"|?*]')
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB hard cap for interactive uploads


def upload_size_bytes(uploaded_file) -> int | None:
    """Best-effort byte size of a Streamlit UploadedFile (its ``.size``)."""
    size = getattr(uploaded_file, "size", None)
    return size if isinstance(size, int) and size >= 0 else None


def upload_exceeds_limit(uploaded_file, *, limit: int = MAX_UPLOAD_BYTES) -> bool:
    """True when the upload reports a size larger than ``limit`` bytes.

    Guards interactive uploads before they are read into memory or parsed.
    A missing/unknown size is treated as within the limit (Streamlit still
    enforces its own server maxUploadSize as a backstop).
    """
    size = upload_size_bytes(uploaded_file)
    return size is not None and size > limit


def human_bytes(num_bytes: int) -> str:
    """Compact human-readable size, e.g. 25 MB, for user-facing messages."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit != "GB" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def safe_storage_filename(filename: str | None, *, fallback: str = "upload.bin") -> str:
    raw_name = str(filename or "").replace("\\", "/")
    candidate = raw_name.rsplit("/", 1)[-1]
    candidate = _CONTROL_CHARS.sub("_", candidate)
    candidate = _UNSAFE_FILENAME_CHARS.sub("_", candidate).strip().strip(".")
    if not candidate:
        candidate = fallback
    stem = candidate.split(".", 1)[0].upper()
    if stem in _RESERVED_WINDOWS_NAMES:
        candidate = f"_{candidate}"
    return candidate[:255]


def safe_child_path(base_dir: Path, filename: str | None, *, fallback: str = "upload.bin") -> Path:
    base = Path(base_dir).resolve()
    child = (base / safe_storage_filename(filename, fallback=fallback)).resolve()
    try:
        child.relative_to(base)
    except ValueError as exc:
        raise ValueError("Resolved file path escapes the storage directory.") from exc
    return child

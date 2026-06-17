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

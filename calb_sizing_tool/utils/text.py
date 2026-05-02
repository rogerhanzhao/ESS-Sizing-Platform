from __future__ import annotations

import re


SCENARIO_LABELS: dict[str, str] = {
    "container_only": "Container Only",
    "cabinet_only": "Cabinet Only",
    "hybrid": "Container + Cabinet",
}


def slugify(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-")
    return cleaned.lower() or fallback


def fmt_dt(value) -> str:
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)

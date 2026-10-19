"""Customer-readable labels; stored sizing and traceability data stay intact."""
from __future__ import annotations

import datetime
import re

_UUID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.I)
_RUN_REFERENCE = re.compile(r"\s*\((?:AC\s+)?run\s+" + _UUID.pattern + r"\)", re.I)


def customer_text(value, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = _UUID.sub("", _RUN_REFERENCE.sub("", str(value)))
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \t]+", " ", text).strip(" /|_- ")
    return text or fallback


def issue_date(value: str | None) -> str:
    """Print a document date without exposing a software timestamp."""
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", str(value or ""))
    if match:
        try:
            date = datetime.date.fromisoformat(match.group())
        except ValueError:
            return customer_text(value)
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        return f"{date.day:02d} {months[date.month - 1]} {date.year}"
    return customer_text(value, datetime.date.today().strftime("%d %b %Y"))


def quantity_label(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def spacing_basis_text(value: str) -> str:
    """Retain distances and references without internal decision-history labels."""
    text = re.sub(r"Owner ruling\s+\d{4}-\d{2}-\d{2}", "Concept design assumption", value, flags=re.I)
    text = re.sub(r"Owner rule\b", "Concept design assumption", text, flags=re.I)
    return re.sub(r"\bowner:\s*", "Concept allowance: ", text, flags=re.I)

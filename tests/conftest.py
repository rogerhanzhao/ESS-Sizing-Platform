from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_CASES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "golden_cases"
SAMPLE_EXCEL_DIR = PROJECT_ROOT / "tests" / "fixtures" / "sample_excels"


def _round_value(value):
    if isinstance(value, dict):
        return {k: _round_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_value(v) for v in value]
    if isinstance(value, float):
        return round(value, 10)
    return value


@pytest.fixture(autouse=True)
def _dispose_cached_db_engines():
    """Dispose engines cached by create_engine_for_url after each test so
    temporary SQLite files can be deleted and no state leaks between tests."""
    yield
    from calb_sizing_tool.infra.db.session import dispose_all_engines

    dispose_all_engines()


@pytest.fixture(scope="session")
def golden_case_dirs() -> list[Path]:
    return sorted(path for path in GOLDEN_CASES_DIR.iterdir() if path.is_dir())


@pytest.fixture(scope="session")
def sample_excel_path() -> Path:
    return SAMPLE_EXCEL_DIR / "dc_dictionary_minimal.xlsx"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_stage3_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


__all__ = [
    "PROJECT_ROOT",
    "GOLDEN_CASES_DIR",
    "SAMPLE_EXCEL_DIR",
    "_round_value",
    "load_json",
    "load_stage3_csv",
]

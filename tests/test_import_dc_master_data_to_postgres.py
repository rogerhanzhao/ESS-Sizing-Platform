from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_import_dc_master_data_to_postgres_dry_run(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/import_dc_master_data_to_postgres.py",
            "--dry-run",
            "--inactive-version",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry_run"
    assert payload["activate_version"] is False
    assert payload["counts"]["cells"] == 4
    assert payload["counts"]["blocks"] == 9
    assert payload["counts"]["publish_batch_items"] == 13
    assert "#" in payload["version_label"]

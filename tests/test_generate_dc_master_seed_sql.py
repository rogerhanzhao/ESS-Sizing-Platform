from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from calb_sizing_tool.config import DC_DATA_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_generate_dc_master_seed_sql_smoke(tmp_path: Path) -> None:
    output = tmp_path / "seed.sql"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_dc_master_seed_sql.py",
            "--inactive-version",
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()

    sql = output.read_text(encoding="utf-8")

    assert "INSERT INTO dictionary_versions" in sql
    assert sql.count("INSERT INTO battery_cell_masters") == 4
    assert sql.count("INSERT INTO battery_cell_revisions") == 4
    assert sql.count("INSERT INTO battery_cell_types") == 4
    assert sql.count("INSERT INTO pack_types") == 4
    assert sql.count("INSERT INTO rack_types") == 3
    assert sql.count("INSERT INTO dc_block_masters") == 9
    assert sql.count("INSERT INTO dc_block_revisions") == 9
    assert sql.count("INSERT INTO dc_block_templates") == 9
    assert sql.count("INSERT INTO soh_profiles") == 12
    assert sql.count("INSERT INTO soh_curve_points") == 252
    assert sql.count("INSERT INTO rte_profiles") == 3
    rte_curve = pd.read_excel(DC_DATA_PATH, sheet_name="rte_curve_314_template")
    expected_rte_curve_points = int(
        (rte_curve["Profile_Id"].notna() & rte_curve["Soh_Band_Min_Pct"].notna()).sum()
    )
    assert sql.count("INSERT INTO rte_curve_points") == expected_rte_curve_points
    assert sql.count("INSERT INTO master_publish_batches") == 1
    assert sql.count("INSERT INTO master_publish_batch_items") == 13
    assert "'dc'" in sql
    assert "FALSE" in sql

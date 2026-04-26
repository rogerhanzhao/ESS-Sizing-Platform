from pathlib import Path

from scripts.generate_sld_renderer_mode_comparison import generate_comparison


def test_generate_sld_renderer_mode_comparison(tmp_path):
    case_dir = Path("tests/fixtures/sld_cases/case01_container_only_group1")
    output_dir = tmp_path / "comparison"

    summary = generate_comparison(case_dir, output_dir)

    assert set(summary["modes"]) == {"engineering_v2", "legacy_server"}
    assert summary["modes"]["engineering_v2"]["metadata"]["renderer_mode"] == "engineering_v2"
    assert summary["modes"]["legacy_server"]["metadata"]["renderer_mode"] == "legacy_server"
    assert summary["modes"]["legacy_server"]["metadata"]["topology_hash"] == summary["modes"]["engineering_v2"]["metadata"]["topology_hash"]
    assert summary["modes"]["legacy_server"]["metadata"]["svg_hash"] != summary["modes"]["engineering_v2"]["metadata"]["svg_hash"]
    assert "topology_v1" not in summary["modes"]
    assert (output_dir / "engineering_v2" / "sld.svg").exists()
    assert (output_dir / "legacy_server" / "sld.svg").exists()
    assert not (output_dir / "topology_v1").exists()
    assert (output_dir / "comparison_summary.md").exists()

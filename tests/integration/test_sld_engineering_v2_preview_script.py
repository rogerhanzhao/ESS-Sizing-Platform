from pathlib import Path

import pytest

from scripts.generate_sld_engineering_v2_preview import generate_preview


def test_generate_sld_engineering_v2_preview(tmp_path):
    output_dir = tmp_path / "engineering_v2_preview"
    metadata = generate_preview(Path("tests/fixtures/sld_cases/case01_container_only_group1"), output_dir)

    svg_path = output_dir / "sld_engineering_v2.svg"
    assert svg_path.exists()
    assert (output_dir / "metadata.json").exists()
    assert (output_dir / "engineering_v2_graph.json").exists()
    assert metadata["model_version"] == "engineering_v2_topology_v1"
    assert metadata["engineering_v2_template"] == "professional_electrical_reference_v1"
    assert metadata["layout_connector_count"] == metadata["edge_count"]
    assert metadata["layout_issue_count"] == 0
    assert metadata["layout_warning_count"] == 4
    assert [warning["issue_id"] for warning in metadata["layout_warnings"]] == [
        "missing_professional_input:MV Cable",
        "missing_professional_input:LV Cable",
        "missing_professional_input:DC Cable",
        "missing_professional_input:BESS Cell",
    ]
    assert metadata["png_width"] == 1780
    assert metadata["png_height"] == 900
    svg_text = svg_path.read_text(encoding="utf-8")
    assert 'viewBox="0 0 1780 900"' in svg_text
    assert "RMU / MV Switchgear" in svg_text
    assert "Cable Connection Vault" in svg_text
    assert "Power Converter System" in svg_text
    assert "LV Busbar=690V" in svg_text
    assert "MISSING: MV cable spec" in svg_text
    assert "Cell: MISSING: BESS cell spec" in svg_text
    assert "TBD" not in svg_text
    assert "DC Isolator/Fuse" in svg_text
    assert "DC BUSBAR" not in svg_text


def test_generate_sld_engineering_v2_preview_supports_multi_dc_block_feeders(tmp_path):
    output_dir = tmp_path / "engineering_v2_preview_multi_dc"
    metadata = generate_preview(
        Path("tests/fixtures/sld_cases/case01_container_only_group1"),
        output_dir,
        dc_blocks_per_feeder=[2, 1, 2, 1],
    )

    svg_text = (output_dir / "sld_engineering_v2.svg").read_text(encoding="utf-8")

    assert metadata["dc_blocks_per_feeder"] == [2, 1, 2, 1]
    assert metadata["layout_issue_count"] == 0
    assert metadata["layout_warning_count"] == 4
    assert metadata["node_count"] == 26
    assert metadata["layout_box_count"] == 26
    assert metadata["png_width"] == 1780
    assert metadata["png_height"] == 900
    assert "DC Block #6" in svg_text
    assert "DC BUSBAR" not in svg_text


def test_generate_sld_engineering_v2_preview_png_is_not_blank(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    output_dir = tmp_path / "engineering_v2_preview_pixels"
    generate_preview(Path("tests/fixtures/sld_cases/case01_container_only_group1"), output_dir)

    with Image.open(output_dir / "sld_engineering_v2.png") as image:
        rgb = image.convert("RGB")
        assert rgb.size == (1780, 900)
        background = rgb.getpixel((0, 0))
        non_background = sum(1 for pixel in rgb.getdata() if pixel != background)

    assert non_background > 25_000


def test_generate_sld_engineering_v2_preview_supports_light_theme(tmp_path):
    output_dir = tmp_path / "engineering_v2_preview_light"
    metadata = generate_preview(
        Path("tests/fixtures/sld_cases/case01_container_only_group1"),
        output_dir,
        theme="light",
    )

    svg_text = (output_dir / "sld_engineering_v2.svg").read_text(encoding="utf-8")

    assert metadata["theme"] == "light"
    assert "#ffffff" in svg_text
    assert "LV Busbar=690V" in svg_text


def test_generate_sld_engineering_v2_preview_accepts_professional_note_specs(tmp_path):
    output_dir = tmp_path / "engineering_v2_preview_specs"
    metadata = generate_preview(
        Path("tests/fixtures/sld_cases/case01_container_only_group1"),
        output_dir,
        theme="light",
        mv_cable_spec="MV-3x1C-240mm2",
        lv_cable_spec="LV-3P+PE-630mm2",
        dc_cable_spec="DC-1x240mm2",
        battery_cell_spec="LFP 3.2V/314Ah",
    )

    svg_text = (output_dir / "sld_engineering_v2.svg").read_text(encoding="utf-8")

    assert metadata["layout_issue_count"] == 0
    assert metadata["layout_warning_count"] == 0
    assert "MV-3x1C-240mm2" in svg_text
    assert "LV-3P+PE-630mm2" in svg_text
    assert "DC-1x240mm2" in svg_text
    assert "Cell: LFP 3.2V/314Ah" in svg_text
    assert "MISSING:" not in svg_text

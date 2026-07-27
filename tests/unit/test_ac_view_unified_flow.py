from pathlib import Path


def test_ac_view_has_one_sizing_trunk_without_legacy_product_preset_control():
    source = (Path(__file__).parents[2] / "calb_sizing_tool" / "ui" / "ac_view.py").read_text(
        encoding="utf-8"
    )

    assert "use_product_preset" not in source
    assert "Run AC Sizing (Governed)" not in source
    assert "standard product AC Block preset" not in source
    assert "grouping_ratio=selected_option.ratio" in source
    assert "dc_grouping_has_feeder_capacity" in source
    assert "ac_block_model_choice_{selected_option.ratio.replace(':', 'to')}" in source
    assert "ac_trunk_product_bind_{selected_option.ratio.replace(':', 'to')}_" in source

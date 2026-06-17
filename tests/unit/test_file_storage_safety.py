from __future__ import annotations

from calb_sizing_tool.utils.files import safe_child_path, safe_storage_filename


def test_safe_storage_filename_strips_path_parts():
    assert safe_storage_filename("../../layout.png") == "layout.png"
    assert safe_storage_filename("..\\layout.png") == "layout.png"


def test_safe_storage_filename_uses_fallback_for_empty_names():
    assert safe_storage_filename("", fallback="fallback.bin") == "fallback.bin"
    assert safe_storage_filename("...", fallback="fallback.bin") == "fallback.bin"


def test_safe_storage_filename_replaces_cross_platform_invalid_chars():
    assert safe_storage_filename('bad:name?.png') == "bad_name_.png"
    assert safe_storage_filename("CON.png") == "_CON.png"


def test_safe_child_path_stays_under_base(tmp_path):
    target = safe_child_path(tmp_path, "../../escape.png")
    assert target.parent == tmp_path.resolve()
    assert target.name == "escape.png"

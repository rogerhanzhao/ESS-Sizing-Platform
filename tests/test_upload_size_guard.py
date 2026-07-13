"""Interactive-upload size guards (admin imports, asset upload, constraint JSON).

Regression for the previously unbounded uploads: oversized files must be
rejected before they are read into memory / parsed.
"""
from calb_sizing_tool.utils.files import (
    MAX_UPLOAD_BYTES,
    human_bytes,
    upload_exceeds_limit,
    upload_size_bytes,
)


class _StubUpload:
    def __init__(self, size):
        self.size = size


def test_within_limit_is_allowed():
    assert not upload_exceeds_limit(_StubUpload(1024), limit=2048)


def test_over_limit_is_rejected():
    assert upload_exceeds_limit(_StubUpload(4096), limit=2048)


def test_exactly_at_limit_is_allowed():
    assert not upload_exceeds_limit(_StubUpload(2048), limit=2048)


def test_unknown_size_is_not_rejected():
    # Streamlit's server maxUploadSize remains the backstop when size is absent.
    assert not upload_exceeds_limit(object())
    assert upload_size_bytes(object()) is None


def test_negative_size_treated_as_unknown():
    assert upload_size_bytes(_StubUpload(-1)) is None


def test_default_limit_is_sane():
    assert MAX_UPLOAD_BYTES == 64 * 1024 * 1024


def test_human_bytes_formats():
    assert human_bytes(25 * 1024 * 1024) == "25 MB"
    assert human_bytes(2 * 1024 * 1024) == "2 MB"
    assert human_bytes(512) == "512 B"

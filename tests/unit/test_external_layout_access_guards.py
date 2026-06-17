from __future__ import annotations

import pytest

from calb_sizing_tool.services.external_layout_service import (
    generate_layout_prompt,
    review_external_layout,
    submit_external_layout_artifact,
)


def test_generate_layout_prompt_requires_logged_in_user():
    with pytest.raises(PermissionError):
        generate_layout_prompt(run_id="run-1", auth_user=None, db_url="sqlite:///:memory:")


def test_submit_external_layout_artifact_requires_logged_in_user():
    with pytest.raises(PermissionError):
        submit_external_layout_artifact(
            run_id="run-1",
            auth_user=None,
            file_bytes=b"image",
            file_name="layout.png",
            media_type="image/png",
            db_url="sqlite:///:memory:",
        )


def test_review_external_layout_requires_admin_reviewer():
    with pytest.raises(PermissionError):
        review_external_layout(
            submission_id="submission-1",
            decision="approve",
            reviewer=None,
            db_url="sqlite:///:memory:",
        )

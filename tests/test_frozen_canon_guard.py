"""Frozen sizing-canon guard — the enforcement half of the change-discipline rule.

SIZING_LOGIC_CANON_V1 declares a set of authoritative DC/AC sizing modules as
FROZEN. This test pins their content by SHA-256 so ANY edit to them fails the
suite loudly, before it can silently change sizing behaviour.

If the canon is ever DELIBERATELY re-approved by the owner, update the pinned
hash in the same commit that changes the module, and record the approval in
docs/CHANGE_DISCIPLINE_V1.md. Never update a hash just to make this test pass.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Authoritative frozen modules (docs/SIZING_LOGIC_CANON_V1.md) -> pinned SHA-256.
FROZEN_CANON_SHA256 = {
    "calb_sizing_tool/services/stage1_service.py": "20b0258c1dfe082087acf8171a2876acbd2a6b17508a49fce1e730c54b31504b",
    "calb_sizing_tool/services/stage2_service.py": "15b6568cf91906da605aeab458cbf0e32fed0fd77f9d8b0c9817c548ecd07086",
    "calb_sizing_tool/services/stage3_service.py": "a38bd529f97b58e8d74fe53ac0867e3ea6e44a273b8cdc45b646a7c1ab80b2ef",
    "calb_sizing_tool/services/dc_pipeline_service.py": "4424c34955ccf01f774ee79d1f111faccd879a8651180e3dcb31fa652a66cb83",
    "calb_sizing_tool/services/ac_sizing_service.py": "ea1dad77ab30630f6695a1d532c0d0d3e37921fb36e07810db0b0556850c0474",
    "calb_sizing_tool/common/ac_block.py": "067468655f88f3512c695f2bb7b1162bc14e87c7eaa0b88a6d8bf9cb99887ed2",
    "calb_sizing_tool/common/allocation.py": "30bfa38462c2903b6fbfec67eea89d3962757ed02b4287010c9611d0b9c22cfa",
}


@pytest.mark.parametrize("rel_path, expected_sha", sorted(FROZEN_CANON_SHA256.items()))
def test_frozen_canon_module_is_unchanged(rel_path: str, expected_sha: str):
    path = _REPO_ROOT / rel_path
    assert path.exists(), f"frozen canon module missing: {rel_path}"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == expected_sha, (
        f"FROZEN sizing module changed: {rel_path}\n"
        f"  expected {expected_sha}\n  actual   {actual}\n"
        "This module is part of SIZING_LOGIC_CANON_V1 and must not change. Revert "
        "the edit. Only update the pinned hash with explicit owner approval (see "
        "docs/CHANGE_DISCIPLINE_V1.md)."
    )

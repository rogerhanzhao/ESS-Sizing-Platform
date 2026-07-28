"""AC Block product transformer field normalization.

Derive topology / LV arrangement from a real datasheet vector group; fall back
to a conservative, clearly-marked standard default only when nothing is stated;
never a PCS-count-based three-winding guess.
"""
from __future__ import annotations

from calb_sizing_tool.services.ac_block_transformer_defaults import (
    BASIS_DATASHEET,
    BASIS_DEFAULT,
    BASIS_DERIVED,
    BASIS_UNCONFIRMED,
    normalize_ac_product_transformer_fields,
    standard_default_vector_group,
    standard_lv_arrangement,
)


def test_standard_defaults_by_winding_count():
    assert standard_default_vector_group(1) == "Dyn11"
    assert standard_default_vector_group(2) == "Dyn11yn11"
    assert standard_lv_arrangement(1) == "common_single_lv_busbar"
    assert standard_lv_arrangement(2) == "independent_lv_busbars"


def test_derive_from_real_three_winding_vector_group():
    # Dy11y11 (two LV tokens) => three-winding, two independent LV busbars.
    out = normalize_ac_product_transformer_fields(
        {"transformer_vector_group": "Dy11y11", "transformer_topology": "three_winding"}
    )
    assert out["lv_winding_count"] == 2
    assert out["transformer_vector_group_basis"] == BASIS_DATASHEET
    assert out["lv_arrangement"] == "independent_lv_busbars"
    assert out["lv_arrangement_basis"] == BASIS_DERIVED


def test_derive_topology_when_only_vector_group_present():
    # Dy11 (one LV token), no topology stated => derived two-winding.
    out = normalize_ac_product_transformer_fields({"transformer_vector_group": "Dy11"})
    assert out["transformer_topology"] == "two_winding"
    assert out["transformer_topology_basis"] == BASIS_DERIVED
    assert out["lv_winding_count"] == 1
    assert out["lv_arrangement"] == "common_single_lv_busbar"


def test_ambiguous_datasheet_text_is_flagged_not_fabricated():
    out = normalize_ac_product_transformer_fields({"transformer_vector_group": "Dy1 or Dy11"})
    # Left as stated; not parsed into a topology/arrangement.
    assert out["transformer_vector_group"] == "Dy1 or Dy11"
    assert out["transformer_vector_group_basis"] == BASIS_UNCONFIRMED
    assert "lv_winding_count" not in out


def test_nothing_stated_uses_conservative_two_winding_default_marked_assumed():
    # A 4-PCS product with no transformer data must NOT be guessed as
    # three-winding by PCS count — the default is a single LV winding, assumed.
    out = normalize_ac_product_transformer_fields({"vendor": "KEHUA"})
    assert out["transformer_topology"] == "two_winding"
    assert out["transformer_topology_basis"] == BASIS_DEFAULT
    assert out["transformer_vector_group"] == "Dyn11"
    assert out["transformer_vector_group_basis"] == BASIS_DEFAULT
    assert out["lv_arrangement"] == "common_single_lv_busbar"
    assert out["lv_arrangement_basis"] == BASIS_DEFAULT


def test_explicit_topology_without_vector_group_fills_matching_default():
    out = normalize_ac_product_transformer_fields({"transformer_topology": "three_winding"})
    assert out["lv_winding_count"] == 2
    assert out["transformer_vector_group"] == "Dyn11yn11"
    assert out["transformer_vector_group_basis"] == BASIS_DEFAULT
    assert out["transformer_topology_basis"] == BASIS_DATASHEET


def test_normalization_is_idempotent():
    once = normalize_ac_product_transformer_fields({"transformer_vector_group": "Dy11y11"})
    twice = normalize_ac_product_transformer_fields(once)
    assert once == twice

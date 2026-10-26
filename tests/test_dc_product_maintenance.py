"""Original DC product maintenance remains draft-only and code-based.

All product values below are synthetic test inputs, not CALB product evidence.
"""
from __future__ import annotations

import io
from copy import deepcopy

import pandas as pd
import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.product_admin_service import ProductAdminService


def _catalogue(path):
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    service = ProductAdminService(url)
    cell_id = service.create_cell(dict(
        cell_code="TEST-CELL-314", model_name="Synthetic 314Ah cell",
        chemistry="LFP", nominal_capacity_ah=314, nominal_voltage_v=3.2,
        is_active=True, is_published=True,
    ))
    parent_id = service.create_dc_block(dict(
        block_code="TEST-PARENT-12", block_name="Synthetic parent",
        product_cell_id=cell_id, cells_in_series=416,
        strings_in_parallel=12, block_form="container",
        container_type="20ft ISO container", gross_energy_mwh=5.01596,
        nominal_voltage_v=1331.2, voltage_min_v=1164.8, voltage_max_v=1497.6,
        nominal_power_kw=2500, max_current_a=2300,
        dimension_width_mm=2438, dimension_depth_mm=6058,
        dimension_height_mm=2896, source_ref="Synthetic parent source",
        is_active=True, is_published=True,
    ))
    return service, cell_id, parent_id


@pytest.fixture
def catalogue(tmp_path):
    return _catalogue(tmp_path / "dc-maintenance.sqlite")


def _tail(**overrides):
    values = dict(
        block_code="TEST-TAIL-10", block_name="Synthetic special tail",
        configuration_role="special_tail", parent_block_code="TEST-PARENT-12",
        cell_code="TEST-CELL-314", cells_in_series=416, strings_in_parallel=10,
        block_form="container", container_type="20ft ISO container",
        # Deliberately independent values: maintenance must never scale a parent.
        gross_energy_mwh=4.1234, nominal_power_kw=1700, max_current_a=1500,
        nominal_voltage_v=1331.2, voltage_min_v=1164.8, voltage_max_v=1497.6,
        dimension_width_mm=2438, dimension_depth_mm=6058,
        dimension_height_mm=2896, source_ref="Synthetic tail source, p. 2",
        version_tag="TEST-V1", usage_restrictions="Special project review required.",
        is_active=True, is_published=True,
    )
    values.update(overrides)
    return values


def _record(service, product_id):
    return next(row for row in service.snapshot()["dc_blocks"]
                if row["product_dc_block_id"] == product_id)


def test_known_wrong_tail_count_is_rejected_even_before_parent_is_chosen(catalogue):
    service, _, _ = catalogue
    before = service.snapshot()
    with pytest.raises(ValueError, match='Child string count'):
        service.create_dc_block(_tail(parent_block_code='', strings_in_parallel=9))
    assert service.snapshot() == before


@pytest.mark.parametrize("role", ["special_tail", "Special tail", "engineering_variant"])
def test_create_resolves_codes_and_keeps_independent_tail_ratings(catalogue, role):
    service, cell_id, parent_id = catalogue
    product_id = service.create_dc_block(_tail(configuration_role=role))
    row = _record(service, product_id)
    assert row["product_cell_id"] == cell_id
    assert row["metadata_json"]["parent_product_id"] == parent_id
    assert row["metadata_json"]["configuration_role"] == "engineering_variant"
    assert row["metadata_json"]["usage_restrictions"] == "Special project review required."
    assert (row["gross_energy_mwh"], row["nominal_power_kw"], row["max_current_a"]) == (4.1234, 1700, 1500)
    assert row["source_ref"] == "Synthetic tail source, p. 2"
    assert row["version_tag"] == "TEST-V1"
    assert row["is_active"] is True and row["is_published"] is True


def test_edit_preserves_unrelated_metadata_and_existing_flags(catalogue):
    service, _, parent_id = catalogue
    product_id = service.create_dc_block(_tail(
        metadata_json={"source_pages": [2, 3], "legacy_note": {"verified": False}},
        is_active=False, is_published=True,
    ))
    assert service.update_record("dc_block", product_id, dict(
        configuration_role="Special tail", parent_block_code="TEST-PARENT-12",
        usage_restrictions="Updated project restriction.",
        source_ref="Synthetic revised source", version_tag="TEST-V2",
        metadata_json={"source_pages": [4]},
    ))
    row = _record(service, product_id)
    assert row["metadata_json"] == {
        "source_pages": [4], "legacy_note": {"verified": False},
        "configuration_role": "engineering_variant", "parent_product_id": parent_id,
        "usage_restrictions": "Updated project restriction.",
    }
    assert row["source_ref"] == "Synthetic revised source"
    assert row["version_tag"] == "TEST-V2"
    assert row["is_active"] is False and row["is_published"] is True


def test_flat_preview_is_non_writing_and_reports_invalid_parent(catalogue):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    preview = service.preview_import_from_df(pd.DataFrame([_tail()]), entity="dc_block")
    assert preview["errors"] == []
    assert len(preview["rows"]) == 1
    invalid = service.preview_import_from_df(
        pd.DataFrame([_tail(parent_block_code="MISSING-PARENT")]), entity="dc_block",
    )
    assert invalid["errors"]
    assert invalid["errors"][0].startswith("Row 2:")
    assert "parent" in invalid["errors"][0].lower()
    assert service.snapshot() == before


def test_export_and_csv_import_preserve_maintained_fields_without_ids(catalogue, tmp_path):
    source, _, _ = catalogue
    source_id = source.create_dc_block(_tail())
    exported = source.export_dc_blocks_dataframe()
    forbidden = {"metadata_json", "product_dc_block_id", "product_cell_id", "created_at", "updated_at"}
    assert not (forbidden & set(exported.columns))
    for field in ("configuration_role", "parent_block_code", "cell_code", "usage_restrictions",
                  "source_ref", "version_tag", "is_active", "is_published"):
        assert field in exported.columns
    tail = exported.loc[exported["block_code"] == "TEST-TAIL-10"]
    csv = pd.read_csv(io.StringIO(tail.to_csv(index=False)), dtype=str)
    target, _, target_parent_id = _catalogue(tmp_path / "roundtrip.sqlite")
    result = target.import_records_from_df("dc_block", csv)
    assert result == {"imported": 1, "skipped": 0, "errors": []}
    restored = next(row for row in target.snapshot()["dc_blocks"] if row["block_code"] == "TEST-TAIL-10")
    original = _record(source, source_id)
    for field in ("block_code", "block_name", "gross_energy_mwh", "nominal_power_kw",
                  "max_current_a", "strings_in_parallel", "source_ref", "version_tag",
                  "is_active", "is_published"):
        assert restored[field] == original[field]
    assert restored["metadata_json"]["parent_product_id"] == target_parent_id
    assert restored["metadata_json"]["usage_restrictions"] == original["metadata_json"]["usage_restrictions"]
    assert restored["metadata_json"]["configuration_role"] == "engineering_variant"


def test_missing_draft_parameters_save_but_remain_explicitly_incomplete(catalogue):
    service, _, _ = catalogue
    product_id = service.create_dc_block(dict(
        block_code="TEST-DRAFT", block_name="Synthetic incomplete tail",
        configuration_role="special_tail", parent_block_code="TEST-PARENT-12",
        source_ref="Synthetic draft source",
    ))
    row = next(row for row in service.dc_block_maintenance_rows()
               if row["product_dc_block_id"] == product_id)
    assert row["configuration_role"] == "special_tail"
    assert row["parent_block_code"] == "TEST-PARENT-12"
    assert row["parameter_status"] == "Incomplete"
    assert row["parameter_details"]
    assert _record(service, product_id)["gross_energy_mwh"] is None
    sizing = service.df_blocks_as_sizing_dataframe().set_index("Dc_Block_Code")
    assert sizing.loc["TEST-DRAFT", "Is_Active"] == 0


def test_unknown_parent_rejected_without_partial_record(catalogue):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError, match="(?i)parent"):
        service.create_dc_block(_tail(parent_block_code="MISSING-PARENT"))
    assert service.snapshot() == before


def test_self_parent_edit_rejected_without_changing_record(catalogue):
    service, _, _ = catalogue
    product_id = service.create_dc_block(_tail())
    before = deepcopy(_record(service, product_id))
    with pytest.raises(ValueError, match="(?i)own parent"):
        service.update_record("dc_block", product_id, dict(parent_block_code="TEST-TAIL-10"))
    assert _record(service, product_id) == before


def test_equal_ah_different_cell_is_not_parent_compatibility(catalogue):
    service, _, _ = catalogue
    service.create_cell(dict(
        cell_code="TEST-OTHER-314", model_name="Another synthetic cell",
        chemistry="LFP", nominal_capacity_ah=314, nominal_voltage_v=3.2,
    ))
    with pytest.raises(ValueError, match="(?i)cell identity"):
        service.create_dc_block(_tail(cell_code="TEST-OTHER-314"))
    assert {row["block_code"] for row in service.snapshot()["dc_blocks"]} == {"TEST-PARENT-12"}


@pytest.mark.parametrize("changed", [
    {"block_form": "cabinet"}, {"cells_in_series": 400},
    {"strings_in_parallel": 12}, {"container_type": "40ft ISO container"},
    {"voltage_min_v": 1100},
])
def test_known_incompatible_flat_tail_declaration_is_rejected(catalogue, changed):
    service, _, _ = catalogue
    with pytest.raises(ValueError):
        service.create_dc_block(_tail(**changed))
    assert len(service.snapshot()["dc_blocks"]) == 1


@pytest.mark.parametrize("values", [
    {"configuration_role": "standard"},
    {"metadata_json": {"configuration_role": "standard"}},
])
def test_marked_special_tail_cannot_demote_by_form_or_metadata(catalogue, values):
    service, _, _ = catalogue
    product_id = service.create_dc_block(_tail())
    with pytest.raises(ValueError, match="(?i)standard"):
        service.update_record("dc_block", product_id, values)
    assert _record(service, product_id)["metadata_json"]["configuration_role"] == "engineering_variant"


def test_special_tail_is_not_a_standard_picker_candidate_even_if_active_published(catalogue):
    service, _, _ = catalogue
    product_id = service.create_dc_block(_tail())
    frame = service.df_blocks_as_sizing_dataframe().set_index("Dc_Block_Code")
    assert frame.loc["TEST-PARENT-12", "Is_Active"] == 1
    assert frame.loc["TEST-PARENT-12", "Is_Default_Option"] == 1
    assert frame.loc["TEST-TAIL-10", "Is_Active"] == 0
    assert _record(service, product_id)["is_published"] is True


def test_legacy_standard_flags_are_not_reinterpreted(catalogue):
    service, _, _ = catalogue
    service.create_dc_block(dict(
        block_code="TEST-LEGACY", block_name="Synthetic legacy standard",
        block_form="container", gross_energy_mwh=5, is_active=True, is_published=False,
        metadata_json={"source_document": "Synthetic old source"},
    ))
    before = deepcopy(service.snapshot())
    rows = service.dc_block_maintenance_rows(before)
    row = next(row for row in rows if row["block_code"] == "TEST-LEGACY")
    assert row["configuration_role"] == "standard"
    frame = service.df_blocks_as_sizing_dataframe().set_index("Dc_Block_Code")
    assert frame.loc["TEST-LEGACY", "Is_Active"] == 1
    assert frame.loc["TEST-LEGACY", "Is_Default_Option"] == 0
    assert service.snapshot() == before


@pytest.mark.parametrize("overrides", [
    {"cell_code": "UNKNOWN-CELL"},
    {"cell_code": "TEST-CELL-314", "product_cell_id": "conflicting-cell-id"},
])
def test_cell_alias_rejects_unknown_or_conflicting_identity(catalogue, overrides):
    service, _, _ = catalogue
    with pytest.raises(ValueError, match="(?i)cell"):
        service.create_dc_block(_tail(**overrides))
    assert len(service.snapshot()["dc_blocks"]) == 1


def test_special_tail_cannot_be_used_as_another_tail_parent(catalogue):
    service, _, _ = catalogue
    service.create_dc_block(_tail())
    with pytest.raises(ValueError, match="(?i)special tail.*parent"):
        service.create_dc_block(_tail(
            block_code="TEST-TAIL-8", parent_block_code="TEST-TAIL-10", strings_in_parallel=8,
        ))


def test_registered_child_cannot_demote_after_marker_is_missing(tmp_path):
    from tests.dc_tail_fixture import make_tail_fixture

    fixture = make_tail_fixture(tmp_path / "registered.sqlite")
    # Simulate a historic registered child whose optional catalogue marker was lost.
    from calb_sizing_tool.infra.db.models import ProductDCBlock
    from calb_sizing_tool.infra.db.session import session_scope

    child_id = fixture.product_ids[10]
    with session_scope(fixture.url) as session:
        session.get(ProductDCBlock, child_id).metadata_json = {}
    with pytest.raises(ValueError, match="(?i)standard"):
        fixture.admin.update_record("dc_block", child_id, {"configuration_role": "standard"})
    frame = fixture.admin.df_blocks_as_sizing_dataframe().set_index("Dc_Block_Code")
    assert frame.loc["SYNTHETIC-10STR", "Is_Active"] == 0


@pytest.mark.parametrize("clear_parent", [False, True])
def test_registered_parent_cannot_be_replaced_or_cleared_through_metadata(tmp_path, clear_parent):
    from tests.dc_tail_fixture import make_tail_fixture

    fixture = make_tail_fixture(tmp_path / "registered-parent.sqlite")
    before = deepcopy(fixture.admin.snapshot())
    declared_parent = None if clear_parent else fixture.product_ids[8]
    with pytest.raises(ValueError, match="(?i)registered.*lineage"):
        fixture.admin.update_record("dc_block", fixture.product_ids[10], dict(
            metadata_json={"parent_product_id": declared_parent},
        ))
    assert fixture.admin.snapshot() == before


def test_flat_parent_code_cannot_conflict_with_metadata_parent_identity(catalogue):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError, match="(?i)parent.*identity differ"):
        service.create_dc_block(_tail(metadata_json={"parent_product_id": "different-parent-id"}))
    assert service.snapshot() == before


@pytest.mark.parametrize("role,metadata_role", [
    ("standard", "engineering_variant"), ("special_tail", "standard"),
])
def test_flat_and_metadata_roles_cannot_conflict(catalogue, role, metadata_role):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError, match="(?i)configuration role conflicts"):
        service.create_dc_block(_tail(
            configuration_role=role, metadata_json={"configuration_role": metadata_role},
        ))
    assert service.snapshot() == before


def test_maintenance_import_remains_create_only(catalogue):
    service, _, _ = catalogue
    product_id = service.create_dc_block(_tail())
    before = deepcopy(_record(service, product_id))
    imported = service.import_records_from_df("dc_block", pd.DataFrame([_tail(
        block_name="Changed by duplicate import", usage_restrictions="Replacement restriction",
    )]))
    assert imported["imported"] == 0 and imported["skipped"] == 1
    assert "already exists" in imported["errors"][0]
    assert _record(service, product_id) == before


@pytest.mark.parametrize("value", ["inf", "-inf", "NaN", float("inf"), float("nan")])
def test_nonfinite_maintenance_rating_is_rejected_without_writing(catalogue, value):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError, match="(?i)finite"):
        service.create_dc_block(_tail(nominal_power_kw=value))
    assert service.snapshot() == before

"""Keep legacy 314Ah sizing from silently consuming an unrelated Admin cell."""
from copy import deepcopy

import pandas as pd
import pytest

from calb_sizing_tool.services.dc_product_curve_guard import check_admin_dc_curve_applicability
from tests.test_dc_page_run_smoke import _app, _dc_run_id, _run_sizing, _state, signed_in_workspace


def _catalogue():
    return {
        "cells": [
            {"product_cell_id": "cell-a", "cell_code": "CALB-314AH-A", "nominal_capacity_ah": 314.0,
             "nominal_voltage_v": 3.2, "manufacturer": "CALB", "chemistry": "LFP"},
            {"product_cell_id": "cell-b", "cell_code": "CALB-314AH-B", "nominal_capacity_ah": 314.0,
             "nominal_voltage_v": 3.2, "manufacturer": "CALB", "chemistry": "LFP"},
            {"product_cell_id": "cell-661", "cell_code": "CALB-661AH", "nominal_capacity_ah": 661.0,
             "nominal_voltage_v": 3.2, "manufacturer": "CALB", "chemistry": "LFP"},
        ],
        "dc_blocks": [
            {"block_code": "C12", "product_cell_id": "cell-a", "default_degradation_curve_code": None},
            {"block_code": "C661", "product_cell_id": "cell-661", "default_degradation_curve_code": "314-default"},
            {"block_code": "CAB", "product_cell_id": "cell-a", "default_degradation_curve_code": None},
        ],
        "degradation_curves": [{
            "curve_code": "314-default", "product_cell_id": "cell-a", "basis_cell_code": "CALB-314AH",
            "data_status": "active_default_314Ah", "is_active": True,
            "metadata_json": {"source_sheets": ["soh_profile_314_data", "soh_curve_314_template"]},
            "cycle_points_json": [{"life_year_index": 0, "soh_pct": 100.0}, {"life_year_index": 1, "soh_pct": 98.0}],
        }],
    }


def _blocks(*, new_cell_active=False):
    return pd.DataFrame([
        {"Dc_Block_Code": "C12", "Dc_Block_Name": "Standard 12-string container", "Block_Form": "container",
         "Block_Nameplate_Capacity_Mwh": 5.01596, "Is_Active": 1, "Is_Default_Option": 1},
        {"Dc_Block_Code": "C661", "Dc_Block_Name": "10.051 MWh container", "Block_Form": "container",
         "Block_Nameplate_Capacity_Mwh": 10.051, "Is_Active": int(new_cell_active), "Is_Default_Option": 1},
        {"Dc_Block_Code": "CAB", "Dc_Block_Name": "418 kWh cabinet", "Block_Form": "cabinet",
         "Block_Nameplate_Capacity_Mwh": 0.418, "Is_Active": 1, "Is_Default_Option": 1},
    ])


def test_legacy_exact_314a_without_curve_code_keeps_original_path():
    result = check_admin_dc_curve_applicability(_blocks(), _catalogue(), forms=("container", "cabinet"))
    assert not result.errors
    assert [row["block_code"] for row in result.selections] == ["C12", "CAB"]


def test_original_picker_selection_is_not_silently_replaced_by_compatible_product():
    blocks = _blocks(new_cell_active=True)
    before = blocks.copy(deep=True)
    result = check_admin_dc_curve_applicability(blocks, _catalogue())
    assert result.selections[0]["block_code"] == "C661"
    assert "CALB-661AH" in result.errors[0]
    assert "not verified" in result.errors[0]
    pd.testing.assert_frame_equal(blocks, before)


def test_original_published_preference_is_preserved():
    blocks = _blocks(new_cell_active=True)
    blocks.loc[blocks.Dc_Block_Code == "C661", "Is_Default_Option"] = 0
    result = check_admin_dc_curve_applicability(blocks, _catalogue())
    assert not result.errors
    assert result.selections[0]["block_code"] == "C12"


@pytest.mark.parametrize("cell_id", ["cell-b", "cell-661", "missing-cell", None])
def test_same_ah_or_copied_314_curve_does_not_authorize_another_exact_cell(cell_id):
    catalogue = _catalogue()
    catalogue["dc_blocks"][0].update(product_cell_id=cell_id, default_degradation_curve_code="314-default")
    assert check_admin_dc_curve_applicability(_blocks(), catalogue).errors


@pytest.mark.parametrize("field,value", [
    ("nominal_capacity_ah", 661), ("nominal_voltage_v", 3.65),
    ("manufacturer", "Other"), ("chemistry", "NMC"), ("cell_code", "OTHER-314AH"),
])
def test_reusing_approved_code_or_ah_cannot_hide_conflicting_cell_data(field, value):
    catalogue = _catalogue()
    catalogue["cells"][0][field] = value
    assert check_admin_dc_curve_applicability(_blocks(), catalogue).errors


@pytest.mark.parametrize("conflict", ["missing", "cell", "source", "inactive"])
def test_explicit_curve_conflicts_block_new_run(conflict):
    catalogue = _catalogue()
    catalogue["dc_blocks"][0]["default_degradation_curve_code"] = "314-default"
    curve = catalogue["degradation_curves"][0]
    if conflict == "missing":
        catalogue["degradation_curves"] = []
    elif conflict == "cell":
        curve["product_cell_id"] = "cell-b"
    elif conflict == "source":
        curve["metadata_json"] = {"source_sheets": ["different_cell_profiles"]}
    else:
        curve["is_active"] = False
    assert check_admin_dc_curve_applicability(_blocks(), catalogue).errors


def test_same_exact_cell_with_explicit_current_curve_is_supported():
    catalogue = _catalogue()
    catalogue["dc_blocks"][0]["default_degradation_curve_code"] = "314-default"
    assert not check_admin_dc_curve_applicability(_blocks(), catalogue).errors


def test_only_requested_forms_are_guarded():
    catalogue = _catalogue()
    catalogue["dc_blocks"][2]["product_cell_id"] = "cell-661"
    assert not check_admin_dc_curve_applicability(_blocks(), catalogue, forms=("container",)).errors
    assert check_admin_dc_curve_applicability(_blocks(), catalogue, forms=("container", "cabinet")).errors


def test_unreadable_catalogue_or_missing_exact_product_fails_closed():
    assert check_admin_dc_curve_applicability(_blocks(), None).errors
    catalogue = _catalogue()
    catalogue["dc_blocks"] = []
    assert check_admin_dc_curve_applicability(_blocks(), catalogue).errors


def _use_catalogue(monkeypatch, *, new_cell_active):
    from calb_sizing_tool.services.product_admin_service import ProductAdminService
    monkeypatch.setattr(ProductAdminService, "df_blocks_as_sizing_dataframe",
                        lambda self: _blocks(new_cell_active=new_cell_active))
    monkeypatch.setattr(ProductAdminService, "snapshot", lambda self: deepcopy(_catalogue()))


def test_admin_new_cell_stops_before_run_id_sizing_and_save(signed_in_workspace, monkeypatch):
    _use_catalogue(monkeypatch, new_cell_active=True)
    app = signed_in_workspace()
    next(radio for radio in app.radio if radio.label == "DC Block Library").set_value("Admin product library")
    app = app.run()
    assert any("10.051 MWh container" in str(item.value) for item in app.caption)
    before = _dc_run_id(app)

    from calb_sizing_tool.ui import dc_view
    def forbidden(*args, **kwargs):
        raise AssertionError("Inapplicable Admin cell must stop before a new run starts")
    for name in ("bump_run_id_dc", "service_run_stage1", "service_size_with_guarantee", "persist_dc_run"):
        monkeypatch.setattr(dc_view, name, forbidden)
    app = _run_sizing(app)
    assert not app.exception
    assert _dc_run_id(app) == before
    assert any("CALB-661AH" in str(item.value) for item in app.error)
    assert any("Excel reference library" in str(item.value) for item in app.error)


def test_excel_path_still_runs_with_unrelated_admin_products_present(signed_in_workspace, monkeypatch):
    _use_catalogue(monkeypatch, new_cell_active=True)
    app = _run_sizing(signed_in_workspace())
    assert not app.exception
    assert _state(app, "dc_result_summary")
    assert _dc_run_id(app)


def test_legacy_314a_admin_run_remains_available_without_new_curve_registration(signed_in_workspace, monkeypatch):
    _use_catalogue(monkeypatch, new_cell_active=False)
    app = signed_in_workspace()
    next(radio for radio in app.radio if radio.label == "DC Block Library").set_value("Admin product library")
    app = _run_sizing(app.run())
    assert not app.exception
    assert _state(app, "dc_result_summary")
    assert _dc_run_id(app)


def test_saved_result_remains_viewable_with_inapplicable_admin_default(signed_in_workspace, monkeypatch):
    _use_catalogue(monkeypatch, new_cell_active=True)
    saved = _run_sizing(signed_in_workspace())
    run_id = _dc_run_id(saved)
    nameplate = next(item.value for item in saved.metric if item.label == "Installed DC Nameplate")
    # Select the saved run before the fresh driver's first render, as on reload.
    app = _app()
    for key in ("auth_context", "active_project_id", "active_project_name", "active_case_id", "active_case_name"):
        app.session_state[key] = saved.session_state[key]
    app.session_state["active_run_id"] = run_id
    app.session_state["main_nav"] = "DC Sizing"
    app.session_state["dc_block_source"] = "Admin product library"
    from calb_sizing_tool.ui import dc_view
    def forbidden(*args, **kwargs):
        raise AssertionError("Reading a saved result must not resize or persist it")
    for name in ("bump_run_id_dc", "service_run_stage1", "service_size_with_guarantee", "persist_dc_run"):
        monkeypatch.setattr(dc_view, name, forbidden)
    app = app.run()
    assert not app.exception
    # Historical DC display reads the snapshot without rewriting runtime output.
    assert next(item.value for item in app.metric if item.label == "Installed DC Nameplate") == nameplate
    assert any("Showing the selected saved result" in str(item.value) for item in app.info)
    assert any(button.label == "Export Technical Sizing Report" for button in app.get("download_button"))
    assert _state(app, "active_run_id") == run_id
    assert not any("Sizing was not run" in str(item.value) for item in app.error)

"""The original AC page suggests a valid starting model without taking over edits."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.services.ac_sizing_service import (
    build_simplified_ac_block_models, generate_ac_sizing_options,
)
from calb_sizing_tool.state import workspace_state
from calb_sizing_tool.ui import ac_view


def _models(dc_count=92, ratio="1:2", power=100, energy=400):
    option = next(item for item in generate_ac_sizing_options(
        dc_count, power, energy, 5.01596) if item.ratio == ratio)
    return option, build_simplified_ac_block_models(option.pcs_recommendations, grouping_ratio=ratio)


def test_92_container_initial_model_uses_115_mw_and_keeps_original_library():
    option, models = _models()
    before = deepcopy(models)
    # The correct 115 MW candidate already exists in the original library.
    # A stale keyed choice can still force the old 230 MW selection on screen.
    index = ac_view._suggested_ac_block_model_index(
        models, option, total_energy_mwh=92 * 5.01596,
        target_energy_mwh=400, target_power_mw=100, dc_block_output_circuits=2)
    assert (models[index].pcs_count, models[index].pcs_kw) == (2, 1250)
    assert models[index].block_size_mw * option.ac_block_count == 115
    assert models == before


def test_starting_model_avoids_an_underpowered_first_library_entry():
    option, models = _models(ratio="1:4")
    assert models[0].block_size_mw * option.ac_block_count == 57.5
    index = ac_view._suggested_ac_block_model_index(
        models, option, total_energy_mwh=92 * 5.01596,
        target_energy_mwh=400, target_power_mw=100, dc_block_output_circuits=2)
    assert models[index].block_size_mw * option.ac_block_count == 115


def test_starting_model_rejects_a_feeder_infeasible_short_group():
    option, models = _models(3, power=2, energy=8)
    index = ac_view._suggested_ac_block_model_index(
        models, option, total_energy_mwh=15, target_energy_mwh=8,
        target_power_mw=2, dc_block_output_circuits=1)
    # This 1:2 allocation contains a 1-DC tail. The library starts at two PCS.
    assert option.dc_blocks_per_ac == [2, 1]
    assert index is None


def test_75mw_300mwh_68_containers_suggest_34_pcs_not_68():
    option, models = _models(68, ratio="1:4", power=75, energy=300)
    index = ac_view._suggested_ac_block_model_index(
        models, option, total_energy_mwh=341.088,
        target_energy_mwh=300, target_power_mw=75, dc_block_output_circuits=2)
    assert option.ac_block_count == 17
    assert (models[index].pcs_count, models[index].pcs_kw) == (2, 2500)
    assert models[index].block_size_mw * option.ac_block_count == 85


def test_starting_model_does_not_recommend_a_known_energy_failure():
    option, models = _models()
    assert ac_view._suggested_ac_block_model_index(
        models, option, total_energy_mwh=300, target_energy_mwh=400,
        target_power_mw=100, dc_block_output_circuits=2) is None


@pytest.mark.parametrize("field", ["total_energy_mwh", "target_energy_mwh", "target_power_mw"])
def test_incomplete_legacy_poi_data_has_no_suggestion_instead_of_a_division_error(field):
    option, models = _models()
    values = dict(total_energy_mwh=461, target_energy_mwh=400, target_power_mw=100,
                  dc_block_output_circuits=2)
    values[field] = 0
    assert ac_view._suggested_ac_block_model_index(models, option, **values) is None


@pytest.fixture()
def original_ac_page(monkeypatch):
    monkeypatch.setattr(ac_view, "resolve_preferred_ac_snapshot",
                        lambda *args, **kwargs: SimpleNamespace(is_persisted=False))
    monkeypatch.setattr(ac_view.st, "segmented_control", lambda label, options, **kwargs:
                        ac_view.st.session_state.get(kwargs["key"], kwargs["default"]))
    from calb_sizing_tool.services import ac_block_product_match
    monkeypatch.setattr(ac_block_product_match, "match_ac_block_products", lambda *a, **kw: [])
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from calb_sizing_tool.ui.ac_view import show\n"
        "st.session_state.setdefault('active_run_id', 'dc92')\n"
        "st.session_state.setdefault('dc_result_summary', {"
        "'container_count': 92, 'cabinet_count': 0, 'total_blocks': 92, "
        "'dc_nameplate_bol_mwh': 461.46832, 'target_mw': 100, 'target_mwh': 400})\n"
        "st.session_state.setdefault('stage13_output', {"
        "'poi_power_req_mw': 100, 'poi_energy_req_mwh': 400})\n"
        "show()\n"
    )
    return app


def test_original_page_suggests_once_preserves_manual_and_restores_on_request(original_ac_page):
    page = original_ac_page.run(timeout=30)
    assert not page.exception
    model = page.selectbox(key="ac_block_model_choice_1to2")
    assert "2 x 1250 kW" in model.options[model.value]
    assert any("115.00 MW" in str(item.value) for item in page.caption)
    manual_index = next(i for i, label in enumerate(model.options) if "2 x 2500 kW" in label)
    model.select(manual_index)
    page = page.run()
    assert not page.exception
    assert page.selectbox(key="ac_block_model_choice_1to2").value == manual_index
    assert any("Selected equipment:" in item.value and "Use recommended model" in item.value
               for item in page.warning)
    page = page.run()
    assert page.selectbox(key="ac_block_model_choice_1to2").value == manual_index
    next(button for button in page.button if button.label == "Use recommended model").click()
    page = page.run()
    assert not page.exception
    model = page.selectbox(key="ac_block_model_choice_1to2")
    assert "2 x 1250 kW" in model.options[model.value]


def test_new_dc_source_does_not_inherit_a_previous_230_mw_widget_choice(original_ac_page):
    page = original_ac_page.run(timeout=30)
    model = page.selectbox(key="ac_block_model_choice_1to2")
    manual_index = next(i for i, label in enumerate(model.options) if "2 x 2500 kW" in label)
    model.select(manual_index)
    page = page.run()
    assert "2 x 2500 kW" in page.selectbox(key="ac_block_model_choice_1to2").options[manual_index]
    page.session_state["active_run_id"] = "new-dc92"
    page = page.run()
    assert not page.exception
    model = page.selectbox(key="ac_block_model_choice_1to2")
    assert "2 x 1250 kW" in model.options[model.value]


def test_original_page_keeps_the_saved_model_over_the_new_suggestion(original_ac_page):
    original_ac_page.session_state["ac_output"] = {
        "source_run_id": "dc92", "selected_ratio": "1:2", "ac_block_grouping_ratio": "1:2",
        "pcs_per_block": 2, "pcs_kw": 2500, "ac_block_model_code": "ACBLK-2X2500KW-20FT",
        "num_blocks": 46, "total_ac_mw": 230,
    }
    page = original_ac_page.run(timeout=30)
    assert not page.exception
    model = page.selectbox(key="ac_block_model_choice_1to2")
    assert "2 x 2500 kW" in model.options[model.value]
    assert any("115.00 MW" in str(item.value) for item in page.caption)


def test_first_visit_to_another_ratio_suggests_its_own_model_and_preserves_later_edits(original_ac_page):
    original_ac_page.session_state["ac_output"] = {
        "source_run_id": "dc92", "selected_ratio": "1:2", "ac_block_grouping_ratio": "1:2",
        "pcs_per_block": 2, "pcs_kw": 1250, "ac_block_model_code": "ACBLK-2X1250KW-20FT",
        "num_blocks": 46, "total_ac_mw": 115,
    }
    page = original_ac_page.run(timeout=30)
    page.session_state["selected_ac_block_grouping"] = "1:4"
    page = page.run()
    assert not page.exception
    model = page.selectbox(key="ac_block_model_choice_1to4")
    assert "2 x 2500 kW" in model.options[model.value]  # 115 MW, not 57.5 MW
    manual = next(i for i, label in enumerate(model.options) if "4 x 2500 kW" in label)
    model.select(manual)
    page = page.run()
    page.session_state["selected_ac_block_grouping"] = "1:2"
    page = page.run()
    model = page.selectbox(key="ac_block_model_choice_1to2")
    assert "2 x 1250 kW" in model.options[model.value]
    page.session_state["selected_ac_block_grouping"] = "1:4"
    page = page.run()
    assert not page.exception
    assert page.selectbox(key="ac_block_model_choice_1to4").value == manual


def test_saved_mix_does_not_offer_a_uniform_action_that_leaves_the_mix_rows_unchanged(original_ac_page):
    original_ac_page.session_state["ac_output"] = {
        "source_run_id": "dc92", "ac_block_grouping_ratio": "1:2",
        "pcs_per_block": 2, "pcs_kw": 2500, "num_blocks": 2, "total_ac_mw": 7.5,
        "ac_block_mixed": True,
        "ac_block_rows": [dict(pcs_count=2, pcs_kw=2500, dc_blocks=46),
                          dict(pcs_count=2, pcs_kw=1250, dc_blocks=46)],
    }
    page = original_ac_page.run(timeout=30)
    assert not page.exception
    assert not any(button.label == "Use recommended model" for button in page.button)
    assert any("MIX rows below determine the actual station total" in str(item.value)
               for item in page.caption)


@pytest.mark.parametrize("save_fails", [False, True])
def test_saving_replaces_the_top_snapshot_only_on_success(original_ac_page, monkeypatch, save_fails):
    saved = {
        "source_run_id": "dc92", "selected_ratio": "1:2", "ac_block_grouping_ratio": "1:2",
        "pcs_per_block": 2, "pcs_kw": 2500, "ac_block_model_code": "ACBLK-2X2500KW-20FT",
        "num_blocks": 46, "total_ac_mw": 230,
        "dc_total_mwh": 461.46832, "poi_energy_mwh": 400, "poi_power_mw": 100,
    }
    original_ac_page.session_state["ac_output"] = deepcopy(saved)
    original_ac_page.session_state["active_ac_run_id"] = "previous-ac"
    monkeypatch.setattr(ac_view, "get_auth_context",
                        lambda: SimpleNamespace(is_guest=False, username="ui-test"))
    monkeypatch.setattr(ac_view, "_saved_tail_parent", lambda *a, **kw: None)
    saves = []

    def save(**kwargs):
        saves.append(deepcopy(kwargs))
        if save_fails:
            raise ValueError("synthetic failure")
        return SimpleNamespace(run_id="new-ac", alternatives=2, reused=False)

    monkeypatch.setattr(ac_view, "persist_ac_run", save)
    monkeypatch.setattr(ac_view, "persist_ac_runtime_snapshot", lambda **kwargs: None)
    page = original_ac_page.run(timeout=30)
    assert not page.exception
    assert next(m.value for m in page.metric if m.label == "Total AC Power") == "230.00 MW"
    next(button for button in page.button if button.label == "Use recommended model").click()
    page = page.run()
    page.selectbox(key="ac_transformer_topology").select("two_winding")
    page = page.run()
    next(button for button in page.button if button.label == "Run AC Sizing").click()
    page = page.run()
    assert not page.exception
    assert len(saves) == 1
    if save_fails:
        assert page.session_state["ac_output"] == saved
        assert page.session_state["active_ac_run_id"] == "previous-ac"
        assert next(m.value for m in page.metric if m.label == "Total AC Power") == "230.00 MW"
        assert any("could not be saved" in str(message.value) for message in page.error)
    else:
        totals = [m.value for m in page.metric if m.label == "Total AC Power"]
        assert totals == ["115.00 MW", "115.00 MW"]
        assert page.session_state["ac_output"]["total_ac_mw"] == 115
        assert page.session_state["active_ac_run_id"] == "new-ac"
        assert any("Single Line Diagram" in button.label for button in page.button)
        # A normal rerun must not turn a successful save into another save or
        # clear the current form because it adopted its own new alternative.
        page = page.run()
        assert not page.exception
        assert len(saves) == 1
        assert "2 x 1250 kW" in page.selectbox(key="ac_block_model_choice_1to2").options[
            page.selectbox(key="ac_block_model_choice_1to2").value]


@pytest.mark.parametrize("switch", ["dc", "ac"])
def test_real_source_switch_clears_model_grouping_custom_and_mix(monkeypatch, switch):
    state = {
        "active_run_id": "dc1", "active_ac_run_id": "ac1",
        "_ac_form_source": ("dc1", "ac1"), "selected_ac_block_grouping": "1:8",
        "ac_block_model_choice_1to2": 0, "custom_pcs_kw": 3000,
        "ac_mixed_enabled_1to2": True, "ac_mixed_pcs_1to2_0": 8,
        "_ac_model_choices": {"ac_block_model_choice_1to2": "old-model"},
        "unrelated_field": "keep",
    }
    monkeypatch.setattr(workspace_state, "st", SimpleNamespace(session_state=state))
    monkeypatch.setattr(ac_view, "st", SimpleNamespace(session_state=state))
    before = deepcopy(state)
    ac_view._sync_ac_form_source("dc1", "ac1")
    assert state == before  # ordinary rerun and metadata changes keep manual edits
    ac_view._sync_ac_form_source("dc2" if switch == "dc" else "dc1", "ac2")
    assert "selected_ac_block_grouping" not in state
    assert "ac_block_model_choice_1to2" not in state
    assert "custom_pcs_kw" not in state
    assert "ac_mixed_enabled_1to2" not in state
    assert "ac_mixed_pcs_1to2_0" not in state
    assert "_ac_model_choices" not in state
    assert state["unrelated_field"] == "keep"


def test_workspace_source_switch_also_clears_keyed_ac_widgets(monkeypatch):
    state = {"active_run_id": "dc1", "selected_ac_block_grouping": "1:8",
             "ac_block_model_choice_1to2": 0, "ac_mixed_kw_1to2_0": 2500}
    monkeypatch.setattr(workspace_state, "st", SimpleNamespace(session_state=state))
    workspace_state.set_active_run("dc2")
    assert "selected_ac_block_grouping" not in state
    assert "ac_block_model_choice_1to2" not in state
    assert "ac_mixed_kw_1to2_0" not in state

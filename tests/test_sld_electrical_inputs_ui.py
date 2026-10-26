"""The disabled RMU voltage follows the source without duplicate defaults."""
import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("voltage, expected", [(None, 24.0), (22.0, 22.0), (33.0, 33.0)])
def test_rmu_voltage_refreshes_without_session_default_warning(monkeypatch, voltage, expected):
    from streamlit.elements.lib import policies

    page = AppTest.from_string('''
import streamlit as st
from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs
render_electrical_inputs(None, "review", mv_nominal_voltage_kv=st.session_state.get("mv"))
''')
    page.session_state["mv"] = voltage
    monkeypatch.setattr(policies, "_shown_default_value_warning", False)
    page.run()
    assert not page.exception
    assert page.number_input(key="review.rmu_rated_kv_derived").value == expected
    assert page.number_input(key="review.rmu_rated_kv_derived").disabled
    assert not any("created with a default value" in str(item.value) for item in page.warning)

    page.session_state["mv"] = 11.0
    monkeypatch.setattr(policies, "_shown_default_value_warning", False)
    page.run()
    assert not page.exception
    assert page.number_input(key="review.rmu_rated_kv_derived").value == 11.0
    assert not any("created with a default value" in str(item.value) for item in page.warning)

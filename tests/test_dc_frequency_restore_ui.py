"""Original DC form restores frequency through its single Session State source."""
import pytest

from tests.test_dc_page_run_smoke import signed_in_workspace


@pytest.mark.parametrize('frequency', [50.0, 60.0, 'TBD'])
def test_restored_frequency_has_one_default_source_and_preserves_next_edit(
        signed_in_workspace, monkeypatch, frequency):
    from streamlit.elements.lib import policies

    page = signed_in_workspace()
    page.session_state['_pending_dc_input_restore'] = {'poi_frequency_option': frequency}
    # Streamlit suppresses subsequent duplicate-default warnings globally. Reset
    # that suppression so every restored value independently exercises the guard.
    monkeypatch.setattr(policies, '_shown_default_value_warning', False)
    page = page.run()
    assert not page.exception
    widget = page.selectbox(key='dc_inputs.poi_frequency_option')
    assert widget.value == frequency
    assert page.session_state['dc_inputs']['poi_frequency_option'] == frequency
    assert not any('created with a default value' in str(item.value) for item in page.warning)

    changed = 60.0 if frequency == 50.0 else 50.0
    widget.set_value(changed)
    page = page.run()
    assert not page.exception
    assert page.selectbox(key='dc_inputs.poi_frequency_option').value == changed
    assert page.session_state['dc_inputs']['poi_frequency_option'] == changed
    assert not any('created with a default value' in str(item.value) for item in page.warning)

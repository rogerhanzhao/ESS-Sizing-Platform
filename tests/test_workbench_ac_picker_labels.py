"""Different saved AC groupings must be distinguishable without displaying IDs."""
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.ui.workbench_view import _ac_alternative_picker_label


def test_same_pcs_and_dc_totals_show_actual_group_count_and_power():
    first = dict(summary=dict(num_blocks=45, pcs_per_block=2, dc_blocks_total=90),
                 output=dict(total_ac_mw=113))
    second = dict(summary=dict(num_blocks=90, pcs_per_block=2, dc_blocks_total=90),
                  output=dict(total_ac_mw=225))
    assert _ac_alternative_picker_label(first, 'AC B') == 'AC B | 45 AC Blocks | 113.00 MW | 90 DC Blocks'
    assert _ac_alternative_picker_label(second, 'AC A') == 'AC A | 90 AC Blocks | 225.00 MW | 90 DC Blocks'


def test_missing_legacy_values_are_not_invented_or_replaced_with_internal_codes():
    item = dict(run_id='long-internal-id', summary=dict(configuration_code='INTERNAL-CODE'), output={})
    assert _ac_alternative_picker_label(item, 'AC C') == 'AC C | Saved AC alternative'


def test_bad_legacy_numeric_values_do_not_leak_nan_or_fail_the_picker():
    item = dict(summary=dict(num_blocks=True, dc_blocks_total=float('nan')),
                output=dict(total_ac_mw=float('inf')))
    assert _ac_alternative_picker_label(item, 'AC D') == 'AC D | Saved AC alternative'


def _picker_page():
    from calb_sizing_tool.ui import workbench_view as view
    view._render_ac_alternative_picker({'run_id': 'dc'})


def test_existing_use_control_selects_the_exact_named_alternative(monkeypatch):
    from calb_sizing_tool.ui import workbench_view as view
    import streamlit as st

    alternatives = [
        dict(run_id='child-newer', summary=dict(num_blocks=45, dc_blocks_total=90), output=dict(total_ac_mw=113)),
        dict(run_id='child-older', summary=dict(num_blocks=90, dc_blocks_total=90), output=dict(total_ac_mw=225)),
    ]
    monkeypatch.setattr(view, 'list_ac_alternatives', lambda parent: alternatives)
    monkeypatch.setattr(view, 'ac_alternative_label', lambda parent, child: {'child-newer': 'B', 'child-older': 'A'}[child])
    monkeypatch.setattr(view, 'get_active_ac_run_id', lambda: st.session_state.get('selected_child'))
    monkeypatch.setattr(view, 'set_active_ac_run', lambda child: st.session_state.update(selected_child=child))
    app = AppTest.from_function(_picker_page).run()
    assert not app.exception
    assert app.selectbox[0].options == [
        'AC B | 45 AC Blocks | 113.00 MW | 90 DC Blocks',
        'AC A | 90 AC Blocks | 225.00 MW | 90 DC Blocks',
    ]
    app.selectbox[0].select_index(1)
    app = app.run()
    next(button for button in app.button if button.label == 'Use').click()
    app = app.run()
    assert not app.exception
    assert app.session_state['selected_child'] == 'child-older'
    assert next(button for button in app.button if button.label == 'Selected').disabled

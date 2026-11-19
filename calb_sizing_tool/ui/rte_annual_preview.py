"""Display one source duty at a time without changing annual RTE results."""
import streamlit as st

from calb_sizing_tool.services.rte_review_service import annual_rte_preview
from calb_sizing_tool.ui._ui import render_static_table
from calb_sizing_tool.ui.curve_labels import family_label, sorted_family_keys


@getattr(st, 'fragment', lambda func: func)
def render_annual_rte_review_preview(payload, key, preferred='soc20.mean'):
    """Keep all read-only selectors local to the current in-memory proposal."""
    family_choices = sorted_family_keys(payload)
    preview_key = f'rte_family_{key}'
    preview_current = st.session_state.get(preview_key, preferred)
    preview_index = family_choices.index(preview_current) if preview_current in family_choices else (
        family_choices.index(preferred) if preferred in family_choices else 0)
    with st.expander('Annual RTE preview (read only)', expanded=False):
        st.info('Filters only change the view. Save and publish include the complete version, regardless of the condition shown. '
                'You can review several conditions, then save and publish once.')
        family = st.selectbox('Preview operating condition', family_choices,
            index=preview_index, format_func=family_label, key=preview_key)
        preview = annual_rte_preview(payload, family)
        st.caption('This preview does not change curve values or sizing settings. It uses monotonic enforcement on and zero project adjustment. Actual sizing uses the project’s saved options and efficiency chain.')
        st.caption('Band matching uses unrounded source SOH. Displayed SOH may be rounded; near a boundary, use the original value to identify the matching interval.')
        render_annual_rte_preview(preview, f'rte_annual_{key}_{family}')


def annual_rte_display_rows(preview, rate, cycles_per_day):
    selected = [row for row in preview
                if row['rate'] == rate and row['cycles_day'] == cycles_per_day
                and row.get('soh_pct') is not None and row.get('dc_rte_pct') is not None]
    if not selected:
        return []
    years = {int(row['year']): row for row in selected}
    show_basis = any(row['legacy_low_soh_fallback'] for row in selected)
    result = []
    for year in range(max(years) + 1):
        row = years.get(year)
        display = {'Year': year,
                   'SOH (%)': f"{row['soh_pct']:.2f}" if row else 'N/A',
                   'DC RTE (%)': f"{row['dc_rte_pct']:.2f}" if row else 'N/A'}
        if show_basis:
            display['Basis'] = ('Low-SOH reference' if row['legacy_low_soh_fallback'] else 'SOH band') if row else 'No source data'
        result.append(display)
    return result


def render_annual_rte_preview(preview, key):
    if not preview:
        st.info('No annual source data are available for this operating condition.')
        return
    rate_col, cycles_col = st.columns(2)
    rates = sorted({row['rate'] for row in preview})
    rate_key = key + '_rate'
    rate_current = st.session_state.get(rate_key, rates[0])
    if rate_current not in rates:
        st.session_state.pop(rate_key, None)
        rate_current = rates[0]
    rate = rate_col.selectbox('Source rate label', rates,
        index=rates.index(rate_current), key=rate_key, format_func=lambda value: f'{value:g}')
    frequencies = sorted({row['cycles_day'] for row in preview if row['rate'] == rate})
    cycles_key = key + '_cycles'
    cycles_current = st.session_state.get(cycles_key, 1.0 if 1.0 in frequencies else frequencies[0])
    if cycles_current not in frequencies:
        st.session_state.pop(cycles_key, None)
        cycles_current = 1.0 if 1.0 in frequencies else frequencies[0]
    cycles = cycles_col.selectbox('Cycles/day', frequencies,
        index=frequencies.index(cycles_current), key=cycles_key, format_func=lambda value: f'{value:g}')
    st.caption(f'Showing one source condition: rate {rate:g} · {cycles:g} cycles/day ({cycles * 365:g} cycles/year).')
    rows = annual_rte_display_rows(preview, rate, cycles)
    if not rows:
        st.info('No annual values are supplied for this rate and cycling frequency.')
        return
    render_static_table(rows)
    st.caption(f"Source data shown through Year {rows[-1]['Year']}. No later years are generated. Percentages are displayed to two decimal places; matching uses the original values.")
    if any(row['SOH (%)'] == 'N/A' for row in rows):
        st.caption('N/A means source data are missing for that year. No missing-year values are filled.')
    if any(row.get('Basis') == 'Low-SOH reference' for row in rows):
        st.caption('Low-SOH reference identifies years using the retained original-model fallback below the labeled SOH bands.')

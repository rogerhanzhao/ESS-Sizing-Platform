"""Standalone DC comparison export from the validated saved run, without sizing."""
from __future__ import annotations

from datetime import date
from io import BytesIO
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from matplotlib.figure import Figure

from calb_sizing_tool.common.render_lock import RENDER_LOCK
from calb_sizing_tool.reporting.customer_presentation import customer_text
from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot
from calb_sizing_tool.services.dc_reduced_string_tail_service import restored_comparison


def _source(parent):
    comparison = restored_comparison(parent)
    if comparison is None:
        raise ValueError("A saved reduced-string DC comparison is required.")
    return comparison, DcPipelineRunSnapshot.model_validate(comparison['snapshot'])


def tail_report_filename(parent):
    comparison, _ = _source(parent)
    name = customer_text(parent.stage1.project_name, 'CALB_Project')
    name = re.sub(r'[^\w-]+', '_', name).strip('_')[:70] or 'CALB_Project'
    return (f"{name}_DC_Comparison_{comparison.get('tail_container_count', 1)}x"
            f"{comparison['selected_tail_strings']}String_{date.today():%Y%m%d}.docx")


def _table(doc, headers, rows, widths):
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    for column, width in zip(table.columns, widths):
        column.width = Inches(width)
    for cell, text, width in zip(table.rows[0].cells, headers, widths):
        cell.width = Inches(width)
        cell.text = text
        shade = OxmlElement('w:shd')
        shade.set(qn('w:fill'), '23496B')
        cell._tc.get_or_add_tcPr().append(shade)
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
    for index, values in enumerate(rows):
        row = table.add_row()
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        for cell, value, width in zip(row.cells, values, widths):
            cell.width = Inches(width)
            cell.text = str(value)
            if index % 2 == 0:
                shade = OxmlElement('w:shd')
                shade.set(qn('w:fill'), 'EFF4F8')
                cell._tc.get_or_add_tcPr().append(shade)
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(3)
                p.paragraph_format.space_after = Pt(3)
                for run in p.runs:
                    run.font.size = Pt(9)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


def _chart(parent, tail):
    with RENDER_LOCK:
        fig = Figure(figsize=(9, 4), facecolor='white')
        ax = fig.subplots()
        for snapshot, label, color, style in (
                (parent, 'Standard 12-string configuration', '#23496b', '-'),
                (tail, 'Reduced-string comparison', '#009cb5', '--')):
            rows = sorted(snapshot.stage3.rows, key=lambda row: row.year_index)
            ax.plot([row.year_index for row in rows], [row.poi_usable_energy_mwh for row in rows],
                    label=label, color=color, linestyle=style, linewidth=2)
        ax.axhline(parent.stage1.poi_energy_req_mwh, color='#a74b35', linestyle=':', label='POI energy target')
        year = parent.stage1.poi_guarantee_year
        checkpoint = next(row for row in tail.stage3.rows if row.year_index == year)
        ax.scatter([year], [checkpoint.poi_usable_energy_mwh], color='#009cb5', zorder=3)
        ax.axvline(year, color='#909aa5', linestyle=':', linewidth=1)
        ax.set(xlabel='Year from COD', ylabel='POI usable energy (MWh)')
        ax.grid(alpha=0.18)
        ax.legend(loc='best', fontsize=9)
        fig.tight_layout()
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=170)
        buffer.seek(0)
        return buffer


def build_tail_dc_report(parent, *, case_name=None, logo_path=None) -> bytes:
    """Read an integrity-checked comparison; never recalculate, save or adopt it."""
    comparison, tail = _source(parent)
    count = parent.stage2.container_count
    tails = comparison.get('tail_container_count', 1)
    strings = comparison['selected_tail_strings']
    inputs = parent.stage1
    year = inputs.poi_guarantee_year
    baseline_year = next(row for row in parent.stage3.rows if row.year_index == year)
    target = inputs.poi_energy_req_mwh
    energy = comparison['poi_energy_at_guarantee_year_mwh']
    baseline = parent.stage2.dc_nameplate_bol_mwh
    reduced = tail.stage2.dc_nameplate_bol_mwh
    reduction = baseline - reduced
    nominal = comparison['nominal_dc_power_mw']
    original_power = count * comparison['basis']['main_energy_raw_mwh'] * 0.5
    passed = comparison['meets_guarantee_year_energy'] and comparison['meets_nominal_dc_power']
    status = 'DC comparison checks passed' if passed else 'DC comparison requirements not met'

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.27), Inches(11.69)
    section.left_margin = section.right_margin = Inches(0.75)
    section.top_margin, section.bottom_margin = Inches(0.85), Inches(0.7)
    section.header_distance = section.footer_distance = Inches(0.3)
    normal = doc.styles['Normal']
    normal.font.name, normal.font.size = 'Calibri', Pt(10)
    normal.paragraph_format.space_after = Pt(6)
    for style in ('Heading 1', 'Heading 2'):
        doc.styles[style].font.color.rgb = RGBColor.from_string('23496B')
    doc.styles['Title'].font.color.rgb = RGBColor(0, 0, 0)
    doc.styles['Title'].font.size = Pt(23)
    # The installed DOCX template may add a decorative title border.
    for style_name in ('Title', 'Normal'):
        for border in doc.styles[style_name].element.findall('.//' + qn('w:pBdr')):
            border.getparent().remove(border)
    header = section.header.paragraphs[0]
    if logo_path:
        header.add_run().add_picture(str(logo_path), width=Inches(1.1))
    else:
        header.add_run('CALB').bold = True
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('DC comparison only  |  Page ').font.size = Pt(8)
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    doc.core_properties.title = 'Reduced String DC Sizing Comparison'
    doc.core_properties.author = 'CALB'
    title = doc.add_paragraph('Reduced String DC Sizing Comparison', 'Title')
    for border in title._p.findall('.//' + qn('w:pBdr')):
        border.getparent().remove(border)
    doc.add_paragraph(f"Project: {customer_text(inputs.project_name)}")
    if case_name:
        doc.add_paragraph(f"Case: {customer_text(case_name)}")
    doc.add_paragraph(f"Export date: {date.today():%d %b %Y}  |  {tails} × {strings}-string containers")
    doc.add_paragraph(
        f"{status}. Total container count remains {count}. This special configuration replaces "
        f"{tails} standard containers with the {strings}-string version. The standard 12-string "
        "configuration remains the active basis for AC sizing, SLD, arrangement and the technical proposal.")

    doc.add_heading('Comparison summary', level=2)
    _table(doc, ['Measure', 'Standard configuration', 'Reduced-string comparison'], [
        ('Total containers', count, count),
        ('12-string containers', count, count - tails),
        (f'{strings}-string containers', 0, tails),
        ('Installed DC energy (MWh)', f'{baseline:.3f}', f'{reduced:.3f}'),
        ('Capacity reduction', 'Reference', f'{reduction:.3f} MWh / {reduction / baseline:.2%}'),
        (f'POI usable energy at Y{year} (MWh)', f'{baseline_year.poi_usable_energy_mwh:.3f}', f'{energy:.3f}'),
        (f'Margin above {target:.3f} MWh at Y{year}', f'{baseline_year.poi_usable_energy_mwh - target:+.3f} MWh', f'{energy - target:+.3f} MWh'),
        (f'POI energy check at Y{year}', 'Pass' if baseline_year.poi_usable_energy_mwh + 1e-6 >= target else 'Not met',
         'Pass' if comparison['meets_guarantee_year_energy'] else 'Not met'),
        ('Nominal DC power at 0.5C (MW)', f'{original_power:.3f}', f'{nominal:.3f}'),
        (f'Margin above {inputs.dc_power_required_mw:.3f} MW DC duty',
         f'{original_power - inputs.dc_power_required_mw:+.3f} MW', f'{nominal - inputs.dc_power_required_mw:+.3f} MW'),
        ('Nominal power check', 'Pass' if original_power + 1e-9 >= inputs.dc_power_required_mw else 'Not met',
         'Pass' if comparison['meets_nominal_dc_power'] else 'Not met'),
    ], [2.65, 1.95, 2.17])
    doc.add_heading('Special configuration equipment', level=2)
    _table(doc, ['Container', 'Quantity', 'Unit energy (MWh)'], [
        (customer_text(item.block_name), item.count, f'{item.unit_capacity_mwh:.3f}')
        for item in tail.stage2.block_config_items
    ], [3.85, 1.0, 1.92])
    doc.add_paragraph(
        f"{tails * (12 - strings)} strings are removed in total. No containers are added to recover a failed check. "
        "Passing the DC checks is not a lifetime power guarantee or approval of PCS connections.")

    doc.add_page_break()
    doc.add_heading('Energy projection and calculation basis', level=1)
    doc.add_paragraph(
        f"POI duty: {inputs.poi_power_req_mw:.3f} MW / {target:.3f} MWh. "
        f"Energy guarantee checkpoint: Y{year} from COD; project life: {inputs.project_life_years} years. "
        "The target line is a comparison reference for all years; the selected guarantee applies at the stated checkpoint.")
    doc.add_picture(_chart(parent, tail), width=Inches(6.7))
    _table(doc, ['Curve selection', 'Standard configuration', 'Reduced-string comparison'], [
        ('Effective DC rate', f'{parent.stage3.meta.effective_c_rate:.4f}C', f'{tail.stage3.meta.effective_c_rate:.4f}C'),
        ('Selected SOH rate', f'{parent.stage3.meta.chosen_soh_c_rate:g}C', f'{tail.stage3.meta.chosen_soh_c_rate:g}C'),
        ('SOH profile cycles per year', parent.stage3.meta.chosen_soh_cycles_per_year, tail.stage3.meta.chosen_soh_cycles_per_year),
        ('Selected RTE rate', f'{parent.stage3.meta.chosen_rte_c_rate:g}C', f'{tail.stage3.meta.chosen_rte_c_rate:g}C'),
    ], [2.65, 1.95, 2.17])
    changed = (parent.stage3.meta.soh_profile_id != tail.stage3.meta.soh_profile_id
               or parent.stage3.meta.rte_profile_id != tail.stage3.meta.rte_profile_id)
    doc.add_paragraph(
        ('Curve selection changed from the standard configuration. ' if changed else 'Curve selection is unchanged. ')
        + 'Both configurations use the standard 314Ah SOH and RTE library and its existing rate and frequency selector. '
        'Reuse for reduced-string containers is a sizing assumption, not a separate supplier warranty.')
    doc.add_paragraph(
        f"Operating assumptions: {inputs.cycles_per_year} cycles/year; DOD {inputs.dod_frac:.2%}; "
        f"FAT-to-COD interval {inputs.sc_time_months} months; DC-to-POI one-way efficiency {inputs.eff_dc_to_poi_frac:.2%}; "
        f"RTE adjustment {inputs.rte_curve_adjust_pp:+.2f} percentage points. Capacity follows the original "
        "314Ah cell-to-container chain; nominal DC power uses 0.5C of raw beginning-of-life capacity.")
    doc.add_paragraph(
        (f"Each of the {tails} reduced-string containers has one DC output and can connect to one PCS only. "
         if strings == 10 else
         f"Each of the {tails} reduced-string containers has two DC outputs; individual output allocation and ratings remain unconfirmed. ")
        + 'This report does not validate PCS matching, per-output current, charge duty, site layout or installation clearances.')

    standard_rows = {row.year_index: row for row in parent.stage3.rows}
    rows = sorted(tail.stage3.rows, key=lambda row: row.year_index)
    for start in range(0, len(rows), 26):
        doc.add_page_break()
        doc.add_heading('Annual DC comparison' + (' continued' if start else ''), level=1)
        doc.add_paragraph(f"Year {year} is the energy guarantee checkpoint. All values below are read from the saved comparison.")
        _table(doc, ['Year', 'Standard POI\nMWh', 'Comparison POI\nMWh', 'POI margin\nMWh', 'Comparison\nDC RTE', 'Comparison\nSystem RTE'], [
            (f'{row.year_index}' + (' *' if row.year_index == year else ''),
             f'{standard_rows[row.year_index].poi_usable_energy_mwh:.3f}',
             f'{row.poi_usable_energy_mwh:.3f}', f'{row.poi_usable_energy_mwh - target:+.3f}',
             f'{row.dc_rte_frac:.2%}', f'{row.system_rte_frac:.2%}') for row in rows[start:start + 26]
        ], [0.47, 1.32, 1.32, 1.18, 1.24, 1.24])
        doc.add_paragraph('* Energy guarantee checkpoint. A negative margin means the POI energy target is not met in that year.')
        exceeding = [row['year_index'] for row in comparison['annual_current_capacity_rate_review']
                     if not row['within_0_5c_current_capacity']]
        doc.add_paragraph(
            (f"The required DC duty first exceeds 0.5C of remaining gross capacity in Y{min(exceeding)}. "
             if exceeding else 'Required DC duty remains within 0.5C of remaining gross capacity over the modeled years. ')
            + 'This supplementary capacity-based review does not model hardware power degradation or establish a lifetime power guarantee.')
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

import copy
import xml.etree.ElementTree as ET
import pytest

from calb_diagrams.mixed_site_concept import mixed_site_from_ac_output
from calb_diagrams.typical_ac_block_arrangement import ac_block_shape_from_ac_output, render_typical_ac_block


@pytest.mark.parametrize('rows,dc,pcs,mw', [
    ([dict(pcs_count=4, pcs_kw=2500, dc_blocks=4)]*8 + [dict(pcs_count=2, pcs_kw=2500, dc_blocks=2)], 34, 34, 85),
    ([dict(pcs_count=4, pcs_kw=1250, dc_blocks=4)]*2 + [dict(pcs_count=2, pcs_kw=1250, dc_blocks=2)], 10, 10, 12.5),
    ([dict(pcs_count=8, pcs_kw=1250, dc_blocks=8), dict(pcs_count=2, pcs_kw=1250, dc_blocks=3)], 11, 10, 12.5),
])
def test_all_equipment_is_drawn_once_with_original_block_geometry(rows, dc, pcs, mw):
    output = dict(ac_block_rows=rows, num_blocks=len(rows), dc_blocks_total=dc)
    original = copy.deepcopy(output)
    result = mixed_site_from_ac_output(output)
    assert output == original
    assert (result.total_dc, result.total_pcs, result.total_mw) == (dc, pcs, mw)
    svg = ET.fromstring(result.svg)
    assert len(svg.findall(".//*[@data-equipment='dc']")) == dc
    assert len(svg.findall(".//*[@data-equipment='station']")) == len(rows)
    for i, block in enumerate(result.blocks, 1):
        reference = render_typical_ac_block(ac_block_shape_from_ac_output(output, i))
        assert (block['width_m'], block['depth_m']) == (reference.envelope_w_m, reference.envelope_d_m)
        assert len(svg.findall(f".//*[@data-equipment='dc'][@data-ac-block='{i}']")) == rows[i-1]['dc_blocks']
        for other in result.blocks[i:]:
            assert (block['x_m']+block['width_m'] <= other['x_m'] or
                    other['x_m']+other['width_m'] <= block['x_m'] or
                    block['y_m']+block['depth_m'] <= other['y_m'] or
                    other['y_m']+other['depth_m'] <= block['y_m'])


def test_missing_or_inconsistent_rows_do_not_invent_a_layout():
    with pytest.raises(ValueError):
        mixed_site_from_ac_output(dict(ac_block_mixed=True, ac_block_breakdown=[{}, {}]))
    with pytest.raises(ValueError):
        mixed_site_from_ac_output(dict(num_blocks=3, ac_block_rows=[
            dict(pcs_count=4, pcs_kw=2500, dc_blocks=4), dict(pcs_count=2, pcs_kw=2500, dc_blocks=2)]))


def test_report_raster_contains_visible_opaque_equipment_not_an_empty_image():
    import io
    from PIL import Image
    from calb_sizing_tool.reporting.report_v2 import _svg_bytes_to_png
    result = mixed_site_from_ac_output(dict(ac_block_rows=[
        dict(pcs_count=4, pcs_kw=2500, dc_blocks=4), dict(pcs_count=2, pcs_kw=2500, dc_blocks=2)]))
    png = _svg_bytes_to_png(result.svg.encode('utf-8'))
    assert png
    image = Image.open(io.BytesIO(png)).convert('RGBA')
    # Fractional canvas edges may be antialiased; the drawing interior is opaque.
    assert image.crop((1, 1, image.width-1, image.height-1)).getchannel('A').getextrema() == (255, 255)
    colors = image.convert('RGB').getcolors(image.width * image.height)
    counts = {rgb: count for count, rgb in colors}
    from PIL import ImageColor
    from calb_diagrams.ac_block_arrangement_v2 import _BOX, _MV_BODY
    from calb_diagrams.site_array_concept import _GROUND
    assert counts.get(ImageColor.getrgb(_GROUND), 0) > image.width * image.height * 0.1
    assert counts.get(ImageColor.getrgb(_BOX), 0) > 1000
    assert counts.get(ImageColor.getrgb(_MV_BODY), 0) > 1000


def test_stale_head_layout_hint_does_not_turn_tail_into_eight_dc_boxes():
    from calb_diagrams.typical_ac_block_arrangement import CENTRAL_STATION_VARIANT
    result = mixed_site_from_ac_output(dict(layout_variant=CENTRAL_STATION_VARIANT, ac_block_rows=[
        dict(pcs_count=8, pcs_kw=1250, dc_blocks=8), dict(pcs_count=2, pcs_kw=1250, dc_blocks=2)]))
    svg = ET.fromstring(result.svg)
    assert len(svg.findall(".//*[@data-equipment='dc'][@data-ac-block='1']")) == 8
    assert len(svg.findall(".//*[@data-equipment='dc'][@data-ac-block='2']")) == 2


@pytest.mark.parametrize('invalid', [0, -1, 1.5, True, float('nan')])
def test_invalid_saved_dc_quantity_is_not_replaced_by_a_head_default(invalid):
    with pytest.raises(ValueError):
        mixed_site_from_ac_output(dict(dc_blocks_per_ac=4, ac_block_rows=[
            dict(pcs_count=4, pcs_kw=2500, dc_blocks=4),
            dict(pcs_count=2, pcs_kw=2500, dc_blocks=invalid)]))


def _preview_app():
    import streamlit as st
    from calb_sizing_tool.ui.site_layout_view import _render_mixed_station_concept
    other = st.checkbox('Other saved allocation')
    rows = [dict(pcs_count=4, pcs_kw=2500, dc_blocks=4),
            dict(pcs_count=2, pcs_kw=2500, dc_blocks=3 if other else 2)]
    _render_mixed_station_concept(dict(ac_block_rows=rows))


def test_existing_page_preview_tracks_current_saved_allocation():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(_preview_app, default_timeout=30).run()
    assert not app.exception
    app.checkbox(key='show_mixed_station_concept').check().run()
    assert not app.exception
    assert any('6 DC containers' in c.value for c in app.caption)
    app.checkbox[0].check().run()
    assert not app.exception
    assert any('7 DC containers' in c.value for c in app.caption)
    assert not any('6 DC containers' in c.value for c in app.caption)


def test_variable_rows_use_actual_widths_mirror_pairs_and_connected_group_roads():
    from dataclasses import replace
    from calb_diagrams.mixed_site_concept import _pack_mixed_rows
    from calb_diagrams.site_array_concept import US_NFPA_SITE
    output=dict(ac_block_rows=[dict(pcs_count=4,pcs_kw=1250,dc_blocks=4)]*4+
                [dict(pcs_count=1,pcs_kw=1250,dc_blocks=1)])
    arrangements=[render_typical_ac_block(ac_block_shape_from_ac_output(output,i+1)) for i in range(5)]
    p=_pack_mixed_rows(arrangements,2,replace(US_NFPA_SITE,fire_access_limit_m=4))
    assert len(p['groups'])==3
    assert len(p['roads'])==len(p['groups'])+1
    assert [b['source_index'] for b in p['blocks']]==list(range(5))
    assert [b['mirrored'] for b in p['blocks']]==[False,True,False,True,False]
    assert p['blocks'][1]['x_m']-p['blocks'][0]['x_m']==pytest.approx(
        arrangements[0].envelope_w_m+US_NFPA_SITE.mv_corridor_m)
    assert all(g['depth_m']/2<=4 for g in p['groups'])
    assert p['roads'][0]==0 and p['roads'][-1]+US_NFPA_SITE.fire_road_m==pytest.approx(p['depth'])


def test_layout_group_ids_and_dimensions_come_from_actual_geometry():
    result=mixed_site_from_ac_output(dict(ac_block_rows=[
        dict(pcs_count=8,pcs_kw=1250,dc_blocks=8),dict(pcs_count=2,pcs_kw=1250,dc_blocks=2)]))
    assert [i for g in result.groups for i in g['block_indices']]==[b['index'] for b in result.blocks]
    assert f'{result.width_m:.1f} x {result.depth_m:.1f} m' in result.svg
    assert 'paired MV corridor' in result.svg
    assert 'door' in result.svg.lower()

"""Concept-only station composition from actual saved per-block shapes.

Single-block geometry stays owned by typical_ac_block_arrangement. This layer
only places those envelopes; it never selects or reallocates equipment.
"""
from dataclasses import dataclass
from dataclasses import replace
from math import isfinite, isclose
import textwrap
from xml.sax.saxutils import escape

from calb_diagrams.ac_block_arrangement_v2 import US_NFPA_OIL
from calb_diagrams.site_array_concept import US_NFPA_SITE
from calb_diagrams.typical_ac_block_arrangement import render_typical_ac_block, ac_block_shape_from_ac_output, arrangement_equipment_placements


def mixed_site_from_ac_output(output):
    """Use recorded rows or legacy per-block arrays; never invent a tail row."""
    rows = output.get('ac_block_rows')
    if not isinstance(rows, list) or not rows:
        counts = output.get('pcs_count_by_block')
        dc = output.get('dc_blocks_per_ac')
        if not isinstance(dc, (list, tuple)):
            dc = output.get('dc_blocks_total_by_block')
        if not isinstance(counts, list) or not isinstance(dc, (list, tuple)) or len(counts) != len(dc):
            raise ValueError('Saved per-block equipment allocation is unavailable.')
        rows = [dict(pcs_count=p, pcs_kw=output.get('pcs_kw'), dc_blocks=d) for p, d in zip(counts, dc)]
    if output.get('governed_groups') or output.get('dc_unit_kind') == 'independent_cabinet_group':
        raise ValueError('This concept view supports manual mixed container stations only.')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Each saved AC Block must contain its equipment allocation.')
        for key in ('pcs_count', 'pcs_kw', 'dc_blocks'):
            value = row.get(key)
            if isinstance(value, bool) or value is None:
                raise ValueError('Saved equipment quantities and ratings must be positive.')
            value = float(value)
            if not isfinite(value) or value <= 0 or (key != 'pcs_kw' and not value.is_integer()):
                raise ValueError('Saved equipment quantities and ratings must be positive; counts must be integers.')
    if len({(r['pcs_count'], r['pcs_kw']) for r in rows}) < 2:
        raise ValueError('Use the existing uniform-station layout for this configuration.')
    for key in ('num_blocks', 'ac_blocks_total'):
        if output.get(key) and int(output[key]) != len(rows):
            raise ValueError('Saved AC Block count does not match its allocation rows.')
    # Manual MIX has no per-row governed layout override. A retained head-model
    # hint must not force every smaller tail into the central 8-DC arrangement.
    shapes = [replace(ac_block_shape_from_ac_output(dict(output, ac_block_rows=rows), i+1),
                      layout_variant='') for i in range(len(rows))]
    result = render_mixed_site_concept(shapes)
    if output.get('dc_blocks_total') and int(output['dc_blocks_total']) != result.total_dc:
        raise ValueError('Saved DC count does not match its allocation rows.')
    if output.get('total_ac_mw') and not isclose(float(output['total_ac_mw']), result.total_mw, abs_tol=1e-6):
        raise ValueError('Saved station power does not match its allocation rows.')
    if output.get('pcs_count_total') and int(output['pcs_count_total']) != result.total_pcs:
        raise ValueError('Saved PCS count does not match its allocation rows.')
    return result


@dataclass(frozen=True)
class MixedSiteConcept:
    svg: str
    blocks: tuple
    width_m: float
    depth_m: float
    total_dc: int
    total_pcs: int
    total_mw: float
    groups: tuple = ()
    roads: tuple = ()


def _pack_mixed_rows(arrangements, columns, site_profile):
    """Place saved blocks in order, using the original site spacing rules.

    Unlike uniform packing, each row has its own widths and maximum depth.
    Group depth uses the same two-sided access-reach assumption as L2.
    """
    road, aisle = site_profile.fire_road_m, site_profile.maintenance_aisle_m
    rows = []
    for start in range(0, len(arrangements), columns):
        batch = arrangements[start:start+columns]
        x, placed, k = 0.0, [], 0
        while k < len(batch):
            a = batch[k]
            pair = k+1 < len(batch) and not a.uses_central_station and not batch[k+1].uses_central_station
            placed.append((start+k, x, False))
            x += a.envelope_w_m
            if pair:
                x += site_profile.mv_corridor_m
                placed.append((start+k+1, x, True))
                x += batch[k+1].envelope_w_m
                k += 2
            else:
                k += 1
            if k < len(batch):
                x += aisle
        rows.append(dict(width=x, depth=max(a.envelope_d_m for a in batch), placements=placed))
    groups, current, depth = [], [], 0.0
    for row in rows:
        if row['depth']/2 > site_profile.fire_access_limit_m:
            raise ValueError('A saved block exceeds the selected concept access-reach assumption.')
        proposed = depth + (aisle if current else 0) + row['depth']
        if current and proposed/2 > site_profile.fire_access_limit_m:
            groups.append(current)
            current, depth = [], 0.0
        depth += (aisle if current else 0) + row['depth']
        current.append(row)
    groups.append(current)
    width = max(r['width'] for r in rows) + 2*road
    y, blocks, group_records, roads = road, [], [], [0.0]
    for gi, group in enumerate(groups, 1):
        top, indices = y, []
        for ri, row in enumerate(group):
            for index, x, mirror in row['placements']:
                a = arrangements[index]
                blocks.append(dict(source_index=index, x_m=road+x,
                                   y_m=y+(row['depth']-a.envelope_d_m)/2,
                                   mirrored=mirror, group=gi, row_top_m=y))
                indices.append(index+1)
            y += row['depth']
            if ri < len(group)-1:
                y += aisle
        group_records.append(dict(index=gi, y_m=top, depth_m=y-top, block_indices=tuple(indices)))
        roads.append(y)
        y += road
    return dict(width=width, depth=y, blocks=blocks, groups=tuple(group_records), roads=tuple(roads))


def render_mixed_site_concept(shapes, profile=US_NFPA_OIL, site_profile=US_NFPA_SITE):
    """Actual heterogeneous blocks, original site style and shared equipment glyphs.

    Search row counts for the smallest equipment/access envelope while retaining
    saved block order. This is not unrestricted site optimisation or approval.
    """
    from calb_diagrams.ac_block_arrangement_v2 import draw_dc_container, draw_mv_station
    from calb_diagrams.site_array_concept import _r, _t, _dim, _GROUND, _ROAD, _BLOCK, _BLOCK_EDGE, _INK
    shapes = tuple(shapes)
    if not shapes or len({s.block_index for s in shapes}) != len(shapes):
        raise ValueError('Unique saved AC Block rows are required.')
    if any(s.dc_blocks < 1 or s.pcs_count < 1 or not isfinite(s.block_power_mw)
           or s.block_power_mw <= 0 for s in shapes):
        raise ValueError('Saved block quantities and ratings must be positive.')
    arrangements = [render_typical_ac_block(s, profile) for s in shapes]
    candidates = [_pack_mixed_rows(arrangements, columns, site_profile)
                  for columns in range(1, len(shapes)+1)]
    packing = min(candidates, key=lambda p: (p['width']*p['depth'], max(p['width'],p['depth'])/min(p['width'],p['depth'])))
    width, depth = packing['width'], packing['depth']
    road, aisle, scale = site_profile.fire_road_m, site_profile.maintenance_aisle_m, 12.0
    canvas_w = max(640.0, width*scale+140)
    title = f'MIXED STATION - CONCEPT SITE ARRANGEMENT | {len(shapes)} AC BLOCKS | {sum(s.block_power_mw for s in shapes):.2f} MW'
    notes = [f'{sum(s.dc_blocks for s in shapes)} DC containers | {sum(s.pcs_count for s in shapes)} PCS | {len(packing["groups"])} layout group(s)',
             f'Equipment + access envelope: {width:.1f} x {depth:.1f} m = {width*depth:,.0f} m2',
             f'Profile assumptions: road {road:g} m; maintenance aisle {aisle:g} m; paired MV corridor {site_profile.mv_corridor_m:g} m.',
             'Roads and corridors are conceptual. Door / cooling-end markers follow the shared block geometry.',
             'CONCEPT ONLY - NOT FOR CONSTRUCTION. Clearances require project and authority confirmation.',
             'Excludes substation, site boundary, drainage, setbacks and final MV routing.']
    wrap = max(40, int((canvas_w-100)/6.3))
    title_lines = textwrap.wrap(title, width=wrap)
    footer = [line for note in notes for line in textwrap.wrap(note, width=wrap)]
    ox, oy = (canvas_w-width*scale)/2, 42+17*len(title_lines)
    canvas_h = oy+depth*scale+65+16*len(footer)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}" font-family="Consolas, monospace">']
    _r(parts, 0, 0, canvas_w, canvas_h, _GROUND, rx=0)
    for i, line in enumerate(title_lines):
        _t(parts, 45, 26+17*i, line, size=12, anchor='start')
    _r(parts, ox, oy, width*scale, depth*scale, '#dfe1dd', '#4a5055', 1.4, rx=0)
    # Connected perimeter loop and group roads, never a new road at every row.
    for x in (0.0, width-road):
        _r(parts, ox+x*scale, oy, road*scale, depth*scale, _ROAD, rx=0)
    for y in packing['roads']:
        _r(parts, ox, oy+y*scale, width*scale, road*scale, _ROAD, rx=0)
        for dx in range(10, int(width*scale)-15, 42):
            _r(parts, ox+dx, oy+(y+road/2)*scale-1, 20, 2, '#e4e6e2', rx=0)
    blocks = []
    for placed in packing['blocks']:
        i = placed['source_index']; shape, a = shapes[i], arrangements[i]
        x, y, mirror = placed['x_m'], placed['y_m'], placed['mirrored']
        equipment = arrangement_equipment_placements(a, profile)
        _r(parts, ox+x*scale, oy+y*scale, a.envelope_w_m*scale, a.envelope_d_m*scale, _BLOCK, _BLOCK_EDGE, 0.7, rx=0)
        _t(parts, ox+x*scale, oy+y*scale-14, f'AC-{shape.block_index:02d} | {shape.block_power_mw:.2f} MW', size=10, anchor='start')
        _t(parts, ox+x*scale, oy+y*scale-3, f'{shape.dc_blocks} DC / {shape.pcs_count} PCS', size=9, anchor='start', weight=500)
        for p in equipment:
            kind = 'station' if p['equipment_type']=='ac_station' else 'dc'
            px = a.envelope_w_m-p['x_m']-p['width_m'] if mirror else p['x_m']
            gx, gy = ox+(x+px)*scale, oy+(y+p['y_m'])*scale
            parts.append(f'<g data-equipment="{kind}" data-ac-block="{shape.block_index}">')
            if kind == 'station':
                vertical = p['height_m'] > p['width_m']
                if mirror:
                    parts.append(f'<g transform="translate({2*gx+p["width_m"]*scale},0) scale(-1,1)">')
                draw_mv_station(parts, scale, gx, gy, length_m=max(p['width_m'],p['height_m']),
                                width_m=min(p['width_m'],p['height_m']), vertical=vertical)
                if mirror:
                    parts.append('</g>')
            else:
                def orientation(value):
                    return {'east':'west','west':'east'}.get(value,value) if mirror else value
                draw_dc_container(parts, scale, gx, gy, width_m=p['width_m'], height_m=p['height_m'],
                                  door_orientation=orientation(p.get('door_orientation','south')),
                                  equipment_end=orientation(p.get('equipment_end')))
            parts.append('</g>')
        blocks.append(dict(index=shape.block_index,x_m=x,y_m=y,width_m=a.envelope_w_m,
                           depth_m=a.envelope_d_m,dc_blocks=shape.dc_blocks,pcs_count=shape.pcs_count,
                           mw=shape.block_power_mw,equipment=equipment,mirrored=mirror,group=placed['group']))
    _dim(parts, ox, oy+depth*scale+20, ox+width*scale, oy+depth*scale+20,
         f'{width:.1f} m equipment/access envelope', above=False, size=10)
    _dim(parts, ox-20, oy, ox-20, oy+depth*scale, f'{depth:.1f} m', size=10)
    for i, line in enumerate(footer):
        _t(parts, 45, canvas_h-16*(len(footer)-i), line, size=10, anchor='start', weight=500)
    parts.append('</svg>')
    return MixedSiteConcept(''.join(parts), tuple(blocks), width, depth,
                            sum(s.dc_blocks for s in shapes),sum(s.pcs_count for s in shapes),
                            sum(s.block_power_mw for s in shapes),
                            tuple(dict(g, block_indices=tuple(shapes[i-1].block_index for i in g['block_indices']))
                                  for g in packing['groups']),packing['roads'])

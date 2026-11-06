"""Concept-only station composition from actual saved per-block shapes.

Single-block geometry stays owned by typical_ac_block_arrangement. This layer
only places those envelopes; it never selects or reallocates equipment.
"""
from dataclasses import dataclass
from dataclasses import replace
from math import ceil, isfinite, isclose
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


def render_mixed_site_concept(shapes, profile=US_NFPA_OIL, site_profile=US_NFPA_SITE):
    """Draw every supplied block, retaining order and per-block geometry.

    Reserved cells use the largest envelope. Each row has an access road tied
    into a perimeter loop. This conservative first-pass arrangement is not the
    uniform engine's minimum-area search or a compliance assessment.
    """
    shapes = tuple(shapes)
    if not shapes or len({s.block_index for s in shapes}) != len(shapes):
        raise ValueError("Unique saved AC Block rows are required.")
    if any(s.dc_blocks < 1 or s.pcs_count < 1 or not isfinite(s.block_power_mw)
           or s.block_power_mw <= 0 for s in shapes):
        raise ValueError("Saved block quantities and ratings must be positive.")
    arrangements = [render_typical_ac_block(s, profile) for s in shapes]
    road = site_profile.fire_road_m
    aisle = site_profile.maintenance_aisle_m
    bw = max(a.envelope_w_m for a in arrangements)
    bd = max(a.envelope_d_m for a in arrangements)
    # Choose a compact rectangle without altering the saved sequence.
    def dimensions(cols):
        rows = ceil(len(shapes) / cols)
        return 2 * road + cols * bw + (cols - 1) * aisle, rows * bd + (rows + 1) * road
    cols = min(range(1, len(shapes) + 1), key=lambda c: (
        max(dimensions(c)) / min(dimensions(c)), dimensions(c)[0] * dimensions(c)[1]))
    width, depth = dimensions(cols)
    scale = 12.0
    w, h = max(800, width * scale + 80), depth * scale + 160
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="Arial, sans-serif">',
             f'<rect width="{w}" height="{h}" fill="white"/>']
    def text(x, y, value, size=16):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="#16395d">{escape(value)}</text>')
    def rect(x, y, rw, rh, fill, extra=""):
        parts.append(f'<rect x="{40+x*scale}" y="{65+y*scale}" width="{rw*scale}" height="{rh*scale}" fill="{fill}" stroke="#7890a5" stroke-width="0.6" {extra}/>')
    text(40, 24, f'MIXED STATION | {len(shapes)} AC BLOCKS | {sum(s.block_power_mw for s in shapes):.2f} MW')
    text(40, 44, f'{sum(s.dc_blocks for s in shapes)} DC containers | {sum(s.pcs_count for s in shapes)} PCS | All saved AC Blocks shown')
    rect(0, 0, width, depth, '#edf1f5')
    rect(road, road, width-2*road, depth-2*road, 'white')
    for row in range(1, ceil(len(shapes)/cols)):
        rect(road, row*(bd+road), width-2*road, road, '#edf1f5')
    blocks = []
    for i, (shape, a) in enumerate(zip(shapes, arrangements)):
        x = road + (i % cols)*(bw+aisle)
        y = road + (i // cols)*(bd+road)
        equipment = arrangement_equipment_placements(a, profile)
        mirror = (i % cols) % 2 == 1 and not a.uses_central_station
        text(40+x*scale, 65+y*scale-18, f'AC-{shape.block_index:02d} | {shape.block_power_mw:.2f} MW', 16)
        text(40+x*scale, 65+y*scale-5, f'{shape.dc_blocks} DC / {shape.pcs_count} PCS', 13)
        rect(x, y, a.envelope_w_m, a.envelope_d_m, '#fafcff')
        for p in equipment:
            kind = 'station' if p['equipment_type']=='ac_station' else 'dc'
            local_x = a.envelope_w_m-p['x_m']-p['width_m'] if mirror else p['x_m']
            rect(x+local_x, y+p['y_m'], p['width_m'], p['height_m'],
                 '#b4c9de' if kind=='station' else '#e2e9cf',
                 f'data-equipment="{kind}" data-ac-block="{shape.block_index}"')
        blocks.append(dict(index=shape.block_index, x_m=x, y_m=y, width_m=a.envelope_w_m,
                           depth_m=a.envelope_d_m, dc_blocks=shape.dc_blocks,
                           pcs_count=shape.pcs_count, mw=shape.block_power_mw, equipment=equipment))
    text(40, h-65, f'Access-road assumption: {road:g} m | Inter-block aisle: {aisle:g} m', 11)
    text(40, h-46, 'Blue: PCS / MV station | Green: DC container | Pale grey: access road', 11)
    text(40, h-27, 'CONCEPT ONLY - NOT FOR CONSTRUCTION', 12)
    text(40, h-10, 'Excludes substation, site boundary, drainage, setbacks and final MV routing.', 10)
    parts.append('</svg>')
    return MixedSiteConcept(''.join(parts), tuple(blocks), width, depth,
                            sum(s.dc_blocks for s in shapes), sum(s.pcs_count for s in shapes),
                            sum(s.block_power_mw for s in shapes))

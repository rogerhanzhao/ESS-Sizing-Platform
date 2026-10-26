"""Pure last-group comparison SVG; never a formal SLD or artifact producer.

The caller must supply the manifest built from the access-controlled, exact
saved DC / AC sources. Its digest protects accidental preview drift, not source
authority. This renderer consumes the saved links and never allocates equipment.
"""
from __future__ import annotations

from html import escape
import math
from typing import Any

from calb_sizing_tool.services.run_persistence_service import _hash_payload


RENDERER_VERSION = 'tail-last-group-comparison-v1'
_WIDTH = 1680


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, label):
    _require(type(value) in (int, float) and math.isfinite(value) and value > 0,
             f'{label} must be a finite positive number.')
    return float(value)


def _integer(value, label):
    _require(type(value) is int and value > 0, f'{label} must be a positive integer.')
    return value


def _validated_group(manifest):
    _require(isinstance(manifest, dict), 'A validated tail comparison manifest is required.')
    _require(manifest.get('contract_type') == 'reduced_string_tail_last_group_sld_preview'
             and manifest.get('schema_version') == 1, 'Unsupported tail comparison manifest.')
    for field, value in [('comparison_only', True), ('diagram_only', True),
                         ('downstream_ready', False), ('engineering_approved', False),
                         ('preview_available', True)]:
        _require(manifest.get(field) is value, 'Only an available, unadopted comparison can be drawn.')
    _require(manifest.get('status') in ('diagram_only', 'diagram_only_with_tbc')
             and manifest.get('blocking_reasons') == [], 'A blocked comparison cannot be drawn.')
    nominal = manifest.get('nominal_review')
    _require(isinstance(nominal, dict) and all(nominal.get(field) is True for field in
             ('source_energy_requirement_met', 'meets_nominal_dc_power', 'topology_valid')),
             'A failed global nominal review cannot be drawn.')
    _require(manifest.get('preview_sha256') == _hash_payload(
        {key: value for key, value in manifest.items() if key != 'preview_sha256'}),
        'The tail comparison manifest changed before rendering.')
    scope, group = manifest.get('scope'), manifest.get('last_group')
    _require(isinstance(scope, dict) and scope.get('kind') == 'last_physical_ac_group_only'
             and isinstance(group, dict), 'An explicit last physical AC group is required.')
    group_index = _integer(group.get('ac_block_index'), 'AC Block index')
    _require(scope.get('ac_block_index') == group_index, 'The comparison scope does not match its group.')
    connections, pcs, windings = (group.get(field) for field in ('connections', 'pcs_items', 'windings'))
    _require(isinstance(connections, list) and 1 <= len(connections) <= 8,
             'The comparison preview supports one to eight actual DC units per group.')
    _require(isinstance(pcs, list) and 1 <= len(pcs) <= 16,
             'The comparison preview supports one to sixteen actual PCS per group.')
    _require(group.get('dc_count') == len(connections), 'The saved DC unit count is inconsistent.')
    _require([item.get('feeder_index') for item in pcs] == list(range(1, len(pcs) + 1)),
             'PCS feeders must retain their complete saved order.')
    for item in pcs:
        _number(item.get('rating_kw'), 'PCS nameplate')
    ids = []
    for position, unit in enumerate(connections, 1):
        _require(isinstance(unit, dict) and unit.get('dc_block_index') == position,
                 'The saved DC unit order is incomplete.')
        unit_id = unit.get('unit_id')
        _require(isinstance(unit_id, str) and unit_id.strip() and unit_id not in ids,
                 'Every DC unit must have its own saved identifier.')
        ids.append(unit_id)
        _number(unit.get('dc_energy_mwh'), 'DC unit energy')
        feeders = unit.get('feeder_indices')
        _require(isinstance(feeders, list) and feeders and len(feeders) == len(set(feeders))
                 and all(type(index) is int and 1 <= index <= len(pcs) for index in feeders),
                 'A DC connection references an unavailable PCS feeder.')
        outputs = _integer(unit.get('output_circuit_count'), 'DC output count')
        _require(len(feeders) <= outputs, 'A DC unit cannot feed more PCS than its declared outputs.')
        is_tail = position == len(connections)
        _require(unit.get('role') == ('tail' if is_tail else 'main'),
                 'Only the final physical DC unit may be the tail.')
        strings = unit.get('strings_in_parallel')
        _require(strings in ((8, 10) if is_tail else (12,)), 'Unexpected DC string count.')
        if is_tail:
            _require(outputs == (1 if strings == 10 else 2), 'Tail output count conflicts with its string version.')
    _require(group.get('tail_count') == 1 and group.get('main_count') == len(connections) - 1,
             'The comparison must contain exactly one final tail.')
    _require(math.isclose(math.fsum(unit['dc_energy_mwh'] for unit in connections),
                         _number(group.get('dc_energy_mwh'), 'Group DC energy'), abs_tol=1e-7),
             'The group energy conflicts with its actual DC units.')
    _require(isinstance(windings, list) and 1 <= len(windings) <= 2,
             'The saved transformer LV assignment is required.')
    winding_feeders, winding_indices, unused_windings = [], [], []
    for winding in windings:
        winding_indices.append(_integer(winding.get('winding_index'), 'LV winding index'))
        indices = winding.get('feeder_indices')
        _require(isinstance(indices, list)
                 and all(type(index) is int and 1 <= index <= len(pcs) for index in indices),
                 'The saved LV assignment contains unavailable PCS feeders.')
        if not indices:
            unused_windings.append(winding['winding_index'])
        winding_feeders.extend(indices)
    _require(sorted(winding_indices) == list(range(1, len(windings) + 1)),
             'The saved LV winding indices must cover every winding exactly once.')
    _require(manifest.get('unused_lv_winding_indices', []) == unused_windings
             and (not unused_windings or manifest.get('status') == 'diagram_only_with_tbc'),
             'Unused LV windings require an explicit TBC comparison status.')
    _require(sorted(winding_feeders) == list(range(1, len(pcs) + 1)),
             'The saved LV assignment must include every PCS exactly once.')
    transformer = group.get('transformer_review')
    _require(isinstance(transformer, dict), 'The original transformer comparison basis is required.')
    _number(transformer.get('total_mva'), 'Transformer comparison basis')
    return group


def render_tail_comparison_svg(manifest: dict[str, Any]) -> str:
    """Draw the exact saved final-group concept without modifying any input.

    No database, artifact, global preview state, sizing or allocation is used.
    A blocked or stale manifest raises ValueError before producing any SVG.
    """
    group = _validated_group(manifest)
    units, pcs, windings = group['connections'], group['pcs_items'], group['windings']
    body_top = 262
    body_height = max(480, len(units) * 126, len(pcs) * 104)
    footer_top = body_top + body_height + 24
    height = footer_top + 230
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{height}" '
             f'viewBox="0 0 {_WIDTH} {height}" role="img" data-renderer-version="{RENDERER_VERSION}" '
             'aria-labelledby="preview-title preview-description">',
             '<title id="preview-title">CALB last AC group comparison only</title>',
             '<desc id="preview-description">Exact saved DC unit and PCS connections for one final AC group. '
             'Not adopted, not a full station SLD, and not for construction.</desc>',
             '<style>text{font-family:Arial,sans-serif;fill:#183550}.muted{fill:#576b7f}'
             '.warning{fill:#945b16}.dc-link{fill:none;stroke:#b35b18;stroke-width:2}'
             '.pending-link{stroke-dasharray:7 5}.lv-link{fill:none;stroke:#527b9e;stroke-width:2;stroke-dasharray:6 5}'
             '.white{fill:white}</style>',
             f'<rect width="{_WIDTH}" height="{height}" fill="white"/>',
             f'<rect x="24" y="24" width="1632" height="{height - 48}" fill="none" stroke="#d1dce6"/>',
             '<rect x="24" y="24" width="1632" height="88" fill="#173b63"/>']

    def attrs(values):
        return ' '.join(f'{escape(key, quote=True)}="{escape(str(value), quote=True)}"'
                        for key, value in values.items())

    def text(x, y, value, size=17, **values):
        clean = ''.join(character for character in str(value)
                        if ord(character) >= 32 or character in '\n\t')
        parts.append(f'<text x="{x:g}" y="{y:g}" font-size="{size}" {attrs(values)}>'
                     f'{escape(clean)}</text>')

    def rect(x, y, width, box_height, **values):
        parts.append(f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{box_height:g}" {attrs(values)}/>')

    def wire(points, **values):
        points_text = ' '.join(f'{x:g},{y:g}' for x, y in points)
        parts.append(f'<polyline points="{points_text}" {attrs(values)}/>')

    text(48, 63, 'CALB  |  LAST AC GROUP CONNECTION COMPARISON', 27,
         **{'class': 'white', 'font-weight': 'bold'})
    text(48, 94, 'COMPARISON ONLY  /  NOT ADOPTED  /  NOT FOR CONSTRUCTION', 18, **{'class': 'white'})
    text(50, 146, f"AC Block {group['ac_block_index']}  |  {group['main_count']} standard 12-string + "
         f"1 reduced-string tail  |  {group['dc_energy_mwh']:.3f} MWh DC", 22,
         **{'font-weight': 'bold'})
    text(50, 179, f"Only this physical group is shown. The preceding "
         f"{manifest['scope']['preceding_ac_group_count']} AC groups are outside this preview.", 17,
         **{'class': 'muted'})
    text(50, 210, 'Actual saved DC units', 18, **{'font-weight': 'bold'})
    text(850, 210, 'Separate PCS nameplates', 18, **{'font-weight': 'bold'})
    text(1165, 210, 'Original LV assignment', 17, **{'font-weight': 'bold'})
    text(50, 235, 'Lines show the saved connection concept; port capability and protection remain TBC.', 17,
         **{'class': 'muted'})

    unit_y = {unit['unit_id']: body_top + body_height * (index + .5) / len(units)
              for index, unit in enumerate(units)}
    pcs_y = {item['feeder_index']: body_top + body_height * (index + .5) / len(pcs)
             for index, item in enumerate(pcs)}

    # Links are below cards in SVG paint order. Every edge comes from one saved
    # unit-to-feeder pair; there is no cross-unit DC bus or new parallel tie.
    for unit_index, unit in enumerate(units):
        feeders = unit['feeder_indices']
        y = unit_y[unit['unit_id']]
        pending = unit['role'] == 'tail' and unit['strings_in_parallel'] == 8
        for link_index, feeder in enumerate(feeders):
            port_y = y + (link_index - (len(feeders) - 1) / 2) * 22
            trunk_x = 574 + (unit_index * 2 + link_index) * 13
            wire([(490, port_y), (trunk_x, port_y), (trunk_x, pcs_y[feeder]), (850, pcs_y[feeder])],
                 **{'class': 'dc-link pending-link' if pending else 'dc-link',
                    'data-kind': 'dc-connection', 'data-unit': unit['unit_id'],
                    'data-feeder': feeder, 'data-input-arrangement': 'TBC' if pending else 'concept'})

    for winding in windings:
        indices = winding['feeder_indices']
        if not indices:
            # Keep the original empty assignment: no invented PCS, terminal,
            # winding capacity or electrical tie is added to make it drawable.
            center = body_top + body_height * (winding['winding_index'] - .5) / len(windings)
            rect(1170, center - 55, 190, 110, fill='#fff5e8', stroke='#c9944e', rx=5,
                 **{'data-kind': 'lv-winding', 'data-winding': winding['winding_index'],
                    'data-unused': 'true', 'stroke-dasharray': '5 4'})
            for offset, label in [(-31, f"LV winding {winding['winding_index']}"),
                                  (-7, 'Unused / no PCS'), (17, 'Termination: TBC'), (41, 'Rating: TBC')]:
                text(1182, center + offset, label, 17, **{'class': 'warning'})
            continue
        ys = [pcs_y[index] for index in indices]
        center = math.fsum(ys) / len(ys)
        x = 1135 + (winding['winding_index'] - 1) * 20
        for feeder in indices:
            wire([(1085, pcs_y[feeder]), (x, pcs_y[feeder]), (x, center), (1170, center)],
                 **{'class': 'lv-link', 'data-kind': 'lv-assignment', 'data-feeder': feeder,
                    'data-winding': winding['winding_index']})
        rect(1170, center - 43, 190, 86, fill='#f0f5f9', stroke='#a9becf', rx=5,
             **{'data-kind': 'lv-winding', 'data-winding': winding['winding_index']})
        text(1182, center - 18, f"LV winding {winding['winding_index']}", 17,
             **{'font-weight': 'bold'})
        pcs_label = (f'PCS: {indices[0]}-{indices[-1]}' if len(indices) > 2
                     and indices == list(range(indices[0], indices[-1] + 1))
                     else f"PCS: {', '.join(map(str, indices))}")
        text(1182, center + 7, pcs_label, 17)
        text(1182, center + 30, 'Assign / kVA: TBC', 17, **{'class': 'warning'})

    transformer_y = body_top + body_height / 2
    rect(1390, transformer_y - 116, 232, 232, fill='#f7f9fb', stroke='#a9becf', rx=5,
         **{'data-kind': 'transformer-basis'})
    transformer = group['transformer_review']
    for offset, value, size in [(-83, 'TRANSFORMER', 18), (-52, 'Original planning basis', 17),
                               (-21, f"{transformer['total_mva']:.3f} MVA", 21),
                               (10, 'Planning estimate' if transformer['is_estimate'] else
                                'Product nameplate', 17),
                               (43, 'Vector / protection: TBC', 17), (69, 'LV winding limits: TBC', 17),
                               (96, 'Equipment approval: TBC', 17)]:
        text(1506, transformer_y + offset, value, size, **{'text-anchor': 'middle'})
    # Intentionally no invented winding-to-transformer terminal / vector symbol.
    text(1390, transformer_y + 146, 'MV / grid interface: TBC', 17, **{'class': 'warning'})

    for unit in units:
        y = unit_y[unit['unit_id']]
        tail = unit['role'] == 'tail'
        rect(50, y - 48, 440, 96, fill='#fff6e9' if tail else '#f3f7fb',
             stroke='#c9944e' if tail else '#a9becf', rx=5,
             **{'data-kind': 'dc-unit', 'data-unit': unit['unit_id'], 'data-role': unit['role'],
                'data-strings': unit['strings_in_parallel'], 'data-energy-mwh': unit['dc_energy_mwh']})
        text(66, y - 22, f"{unit['unit_id']}  |  {'TAIL' if tail else 'STANDARD'}  |  "
             f"{unit['strings_in_parallel']}-string", 19, **{'font-weight': 'bold'})
        outputs = unit['output_circuit_count']
        interface = (f"{outputs} DC output{'s' if outputs != 1 else ''}" if tail else
                     f"{outputs} configured PCS branch{'es' if outputs != 1 else ''}")
        text(66, y + 4, f"{unit['dc_energy_mwh']:.3f} MWh  |  {interface}", 17)
        if tail and unit['strings_in_parallel'] == 8:
            note = ('2 outputs / 1 PCS: input arrangement TBC' if len(unit['feeder_indices']) == 1 else
                    '2 output links; per-output duty / current TBC')
        elif tail:
            note = '1 DC output -> 1 PCS; electrical ratings TBC'
        else:
            note = 'Saved output mapping; input capability TBC'
        text(66, y + 30, note, 17, **{'class': 'warning' if tail else 'muted'})

    for item in pcs:
        feeder = item['feeder_index']
        y = pcs_y[feeder]
        rect(850, y - 39, 235, 78, fill='#eaf2fa', stroke='#567ea3', rx=5,
             **{'data-kind': 'pcs', 'data-feeder': feeder, 'data-rating-kw': item['rating_kw']})
        text(868, y - 13, f"PCS {feeder}  |  {item['rating_kw']:g} kW", 20, **{'font-weight': 'bold'})
        duty = item.get('required_ac_duty_kw')
        text(868, y + 11, 'AC ref duty: TBC' if duty is None else f'AC ref: {duty:.2f} kW', 17)
        text(868, y + 30, 'V / I / ports: TBC', 17, **{'class': 'muted'})

    rect(50, footer_top, 1572, 172, fill='#fff5e8', stroke='#d5b17a', rx=5)
    text(68, footer_top + 31, 'COMPARISON ONLY  /  NOT ADOPTED  /  NOT FOR CONSTRUCTION', 21,
         **{'font-weight': 'bold', 'class': 'warning'})
    notes = [
        'This is the saved last-group connection comparison, not the active SLD or a full-station electrical design.',
        'Owner 0.5C is a nominal design basis. Reference duty is not a hardware limit or a lifetime power guarantee.',
        'Dashed DC links have an unconfirmed output / input arrangement. No equal split or parallel permission is assumed.',
        'PCS compatibility, output currents, LV winding ratings, transformer protection and MV interface require confirmation.',
    ]
    for index, note in enumerate(notes):
        text(68, footer_top + 61 + index * 26, note, 17)
    text(50, height - 34, 'Last physical AC group only  |  Electrical connection concept - not to scale', 17,
         **{'class': 'muted'})
    parts.append('</svg>')
    return ''.join(parts)


__all__ = ['RENDERER_VERSION', 'render_tail_comparison_svg']

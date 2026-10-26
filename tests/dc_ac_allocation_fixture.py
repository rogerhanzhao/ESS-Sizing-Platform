"""Synthetic allocation mechanism fixtures; never released equipment evidence."""
from copy import deepcopy
import json
from types import SimpleNamespace

from calb_sizing_tool.services.dc_composition_comparison_service import evaluate_dc_composition
from calb_sizing_tool.services.dc_product_comparison_service import package_sha256
from tests.dc_tail_fixture import make_tail_fixture


def json_comparison(comparison):
    """Reproduce C2b's export boundary without changing numeric representations."""
    return json.loads(json.dumps({
        key: value.model_dump(mode='json') if hasattr(value, 'model_dump') else value
        for key, value in comparison.items()
    }, allow_nan=False))


def resign_comparison(comparison):
    comparison['comparison_sha256'] = package_sha256({
        key: value.model_dump(mode='json') if hasattr(value, 'model_dump') else value
        for key, value in comparison.items() if key != 'comparison_sha256'
    })
    return comparison


def make_allocation(comparison):
    manifest = comparison['manifest']
    units = manifest['physical_units']
    allocation = dict(
        contract_type='dc_ac_allocation_v1', schema_version=1,
        source=dict(dc_manifest_sha256=manifest['manifest_sha256'],
                    candidate_comparison_sha256=comparison['comparison_sha256']),
        ac_blocks=[dict(ac_block_id='AC-01')],
        pcs_instances=[], input_ports=[],
        transformer_instances=[dict(transformer_id='TX-01', ac_block_id='AC-01',
                                    capability_ref=None)],
        lv_windings=[dict(transformer_id='TX-01', winding_id='LV-1', lv_bus_id='LV-BUS-01')],
        unit_assignments=[], dc_connections=[], lv_connections=[],
    )
    for index, unit in enumerate(units, start=1):
        pcs_id = f'PCS-{index:02d}'
        allocation['pcs_instances'].append(dict(pcs_id=pcs_id, ac_block_id='AC-01',
                                                capability_ref=None))
        allocation['input_ports'].append(dict(pcs_id=pcs_id, port_id='IN-1',
                                              dc_bus_id=f'DC-BUS-{index:02d}'))
        allocation['unit_assignments'].append(dict(unit_id=unit['unit_id'], ac_block_id='AC-01'))
        allocation['dc_connections'].extend(dict(domain_id=domain_id, pcs_id=pcs_id, port_id='IN-1')
                                               for domain_id in unit['electrical_domain_ids'])
        allocation['lv_connections'].append(dict(pcs_id=pcs_id, transformer_id='TX-01', winding_id='LV-1'))
    return allocation


def make_allocation_fixture(path, *, tail_power_kw=2500, split_outputs=False, tail_strings=10,
                            split_domains=None, explicit_partitions=True):
    library = make_tail_fixture(path, tail_power_kw=tail_power_kw)
    selected = [library.revision_ids[12], library.revision_ids[tail_strings]]
    partitions = {key: deepcopy(library.partitions[key]) for key in selected}
    if split_outputs or split_domains:
        for revision, rows in partitions.items():
            whole = rows[0]
            partitions[revision] = [dict(
                domain_label=f'Synthetic independent output {index + 1}',
                strings=whole['strings'] // 2,
                gross_energy_mwh=whole['gross_energy_mwh'] / 2,
                nominal_power_kw=whole['nominal_power_kw'] / 2,
                max_current_a=whole['max_current_a'] / 2,
                evidence_ref='Synthetic explicit two-output drawing',
            ) for index in range(2)]
    comparison = evaluate_dc_composition(
        library.revisions,
        [dict(revision_id=selected[0], quantity=1, role='main'),
         dict(revision_id=selected[1], quantity=1, role='tail')],
        library.case, library.baseline,
        {key: library.packages[key] for key in selected},
        {key: library.digests[key] for key in selected},
        variant_service=library.variants,
        allow_special_configurations=True, special_reason='Synthetic allocation mechanism study',
        temperature_c=25, standby_soc_pct=50,
        electrical_partitions=partitions if explicit_partitions else None,
    )
    return SimpleNamespace(lib=library, library=library, comparison=comparison,
                           allocation=make_allocation(comparison), partitions=partitions,
                           expected_comparison_sha256=comparison['comparison_sha256'])

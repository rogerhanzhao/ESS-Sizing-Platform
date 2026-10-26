"""Synthetic D1b equipment evidence and duties; never CALB product data."""
from copy import deepcopy
from types import SimpleNamespace

from calb_sizing_tool.services.ac_equipment_capability_service import EquipmentCapabilityRevisionService
from calb_sizing_tool.services.dc_composition_comparison_service import evaluate_dc_composition
from tests.dc_ac_allocation_fixture import make_allocation, make_allocation_fixture


def register_equipment_package(study, package, *, status='candidate_only'):
    """Create a fresh immutable SYNTHETIC revision and return its reference."""
    revision_id = study.capability_service.create(
        package, 'SYNTHETIC mechanism fixture / not manufacturer approval')
    if status in ('parameter_review', 'candidate_only'):
        study.capability_service.transition(
            revision_id, 'draft', 'parameter_review', 'SYNTHETIC parameter review')
    if status == 'candidate_only':
        study.capability_service.transition(
            revision_id, 'parameter_review', 'candidate_only', 'SYNTHETIC candidate-only review')
    elif status == 'retired':
        study.capability_service.transition(
            revision_id, 'draft', 'retired', 'SYNTHETIC retirement')
    elif status not in ('draft', 'parameter_review'):
        raise ValueError('Unsupported synthetic capability status')
    detail = study.capability_service.inspect(revision_id)
    return revision_id, dict(
        package_code=detail['package_code'], revision=detail['revision'],
        sha256=detail['sha256'], evidence_ref='SYNTHETIC equipment source reference')


def replace_equipment_package(study, equipment_id, mutate, *, status='candidate_only'):
    """Review a new package revision without mutating any registered payload."""
    package = deepcopy(study.capability_packages[equipment_id])
    package['revision'] = 'SYNTHETIC-R' + str(study.next_revision)
    study.next_revision += 1
    mutate(package)
    revision_id, reference = register_equipment_package(study, package, status=status)
    instances = (study.allocation['pcs_instances'] if package['kind'] == 'pcs'
                 else study.allocation['transformer_instances'])
    id_field = 'pcs_id' if package['kind'] == 'pcs' else 'transformer_id'
    next(row for row in instances if row[id_field] == equipment_id)['capability_ref'] = reference
    study.capability_packages[equipment_id] = package
    study.capability_revision_ids[equipment_id] = revision_id
    return revision_id


def _pcs_package(identity, *, split_outputs):
    count = 2 if split_outputs else 1
    return dict(
        schema_version=1, package_code='SYNTHETIC-' + identity, revision='SYNTHETIC-R1',
        kind='pcs', model='SYNTHETIC PCS / not a CALB product',
        manufacturer='SYNTHETIC mechanism only', source_ref='SYNTHETIC PCS rating declaration',
        conditions=dict(temperature_min_c=-20, temperature_max_c=50, frequency_hz=50),
        pcs=dict(dc_voltage_min_v=800, dc_voltage_max_v=1500,
            continuous_dc_current_a=5000, dc_discharge_power_kw=3000,
            ac_discharge_power_kw=3000, ac_apparent_power_kva=3300, ac_voltage_v=690,
            aggregate_current_basis='sum_of_port_currents',
            ports=[dict(port_id=f'IN-{index}', dc_bus_group=f'B{index}',
                voltage_min_v=800, voltage_max_v=1500, continuous_current_a=5000,
                discharge_power_kw=3000) for index in range(1, count + 1)],
            dc_buses=[dict(dc_bus_group=f'B{index}') for index in range(1, count + 1)]),
    )


def _transformer_package():
    return dict(
        schema_version=1, package_code='SYNTHETIC-TX-01', revision='SYNTHETIC-R1',
        kind='transformer', model='SYNTHETIC transformer / not a CALB product',
        manufacturer='SYNTHETIC mechanism only', source_ref='SYNTHETIC transformer rating declaration',
        conditions=dict(temperature_min_c=-20, temperature_max_c=50, frequency_hz=50),
        transformer=dict(total_kva=5000, hv_voltage_kv=33, vector_group='SYNTHETIC-Dyn11',
            windings=[dict(winding_id='LV-1', voltage_v=690, continuous_kva=5000)]),
    )


def make_equipment_fixture(path, *, tail_power_kw=2500, cable_eff_pct=100,
                           pcs_eff_pct=100, split_outputs=False, case_overrides=None, tail_strings=10):
    study = make_allocation_fixture(
        path, tail_power_kw=tail_power_kw, split_outputs=split_outputs, tail_strings=tail_strings)
    lib = study.lib
    if cable_eff_pct != 100 or pcs_eff_pct != 100 or case_overrides:
        # Re-run the actual frozen Stage1/Stage3 orchestration. Do not edit or
        # re-sign any previously computed source result to simulate losses.
        updates = dict(eff_dc_cables=cable_eff_pct, eff_pcs=pcs_eff_pct)
        updates.update(case_overrides or {})
        lib.case = lib.case.model_copy(update=updates)
        selected = [lib.revision_ids[12], lib.revision_ids[tail_strings]]
        study.comparison = evaluate_dc_composition(
            lib.revisions,
            [dict(revision_id=selected[0], quantity=1, role='main'),
             dict(revision_id=selected[1], quantity=1, role='tail')],
            lib.case, lib.baseline,
            {key: lib.packages[key] for key in selected},
            {key: lib.digests[key] for key in selected},
            variant_service=lib.variants,
            allow_special_configurations=True,
            special_reason='Synthetic allocation mechanism study',
            temperature_c=25, standby_soc_pct=50,
            electrical_partitions=study.partitions,
        )
        study.allocation = make_allocation(study.comparison)
        study.expected_comparison_sha256 = study.comparison['comparison_sha256']
    if split_outputs:
        # Explicit independent ports mirror the supplied two-domain fixture;
        # nothing is derived from an actual product's rack/string count.
        for pcs in study.allocation['pcs_instances']:
            identity = pcs['pcs_id']
            study.allocation['input_ports'].append(dict(
                pcs_id=identity, port_id='IN-2', dc_bus_id=f'{identity}/DC-BUS-2'))
            links = [row for row in study.allocation['dc_connections'] if row['pcs_id'] == identity]
            links[1]['port_id'] = 'IN-2'
    result = SimpleNamespace(
        lib=lib, library=lib, study=study, comparison=study.comparison,
        allocation=study.allocation, expected_comparison_sha256=study.expected_comparison_sha256,
        capability_service=EquipmentCapabilityRevisionService(lib.actor, lib.url),
        duty_basis=dict(ambient_temperature_c=25, power_factor_abs=0.95,
            mv_bus_voltage_kv=33, passive_dc_path_confirmed=True,
            evidence_ref='SYNTHETIC declared discharge study / no approval'),
        capability_revision_ids={}, capability_packages={}, next_revision=2,
    )
    for pcs in result.allocation['pcs_instances']:
        identity = pcs['pcs_id']
        package = _pcs_package(identity, split_outputs=split_outputs)
        revision_id, reference = register_equipment_package(result, package)
        pcs['capability_ref'] = reference
        result.capability_revision_ids[identity] = revision_id
        result.capability_packages[identity] = package
    package = _transformer_package()
    revision_id, reference = register_equipment_package(result, package)
    result.allocation['transformer_instances'][0]['capability_ref'] = reference
    result.capability_revision_ids['TX-01'] = revision_id
    result.capability_packages['TX-01'] = package
    return result

"""Pure connectivity checks for the new, comparison-only allocation contract.

This module does not certify DC buses, choose equipment, calculate ratings,
modify the original sizing path, or invoke any existing diagram generator.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable, Iterable, TypeVar

from calb_sizing_tool.schemas.dc_ac_allocation import DcAcAllocation


_T = TypeVar("_T")


def validate_allocation_topology(allocation: DcAcAllocation, manifest: dict) -> dict:
    """Validate exact declared connectivity without assuming electrical approval.

    Manifest signatures and current source reviews are checked by the service
    orchestrator. Here the supplied manifest's own ownership register must still
    be internally complete; no domain count or equipment rating is inferred.
    """
    errors: list[str] = []
    pending: list[str] = [
        "Declared connectivity has not been verified against manufacturer capability evidence."
    ]

    def registry(rows: Iterable[_T], key: Callable[[_T], object], label: str) -> dict:
        indexed = {}
        for row in rows:
            identity = key(row)
            if identity in indexed:
                errors.append(f"Duplicate {label}: {identity}.")
            else:
                indexed[identity] = row
        return indexed

    def manifest_rows(field: str, identity: str) -> dict:
        rows = manifest.get(field) if isinstance(manifest, dict) else None
        if not isinstance(rows, list) or not rows:
            errors.append(f"Manifest {field} must be a non-empty explicit register.")
            return {}
        result = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get(identity), str) or not row[identity]:
                errors.append(f"Manifest {field} row {index + 1} has no valid {identity}.")
                continue
            name = row[identity]
            if name in result:
                errors.append(f"Duplicate manifest {identity}: {name}.")
            else:
                result[name] = row
        return result

    units = manifest_rows("physical_units", "unit_id")
    domains = manifest_rows("electrical_domains", "domain_id")
    domains_by_unit: dict[str, set[str]] = defaultdict(set)
    for domain_id, domain in domains.items():
        unit_id = domain.get("unit_id")
        if not isinstance(unit_id, str) or unit_id not in units:
            errors.append(f"Manifest domain {domain_id} references unknown physical unit {unit_id}.")
        else:
            domains_by_unit[unit_id].add(domain_id)
    for unit_id, unit in units.items():
        declared = unit.get("electrical_domain_ids")
        if (not isinstance(declared, list) or not declared
                or any(not isinstance(item, str) or not item for item in declared)):
            errors.append(f"Manifest physical unit {unit_id} has no complete electrical domain list.")
            continue
        if len(set(declared)) != len(declared):
            errors.append(f"Manifest physical unit {unit_id} repeats an electrical domain identity.")
        if set(declared) != domains_by_unit.get(unit_id, set()):
            errors.append(f"Manifest physical unit {unit_id} domain ownership does not match its register.")

    ac_blocks = registry(allocation.ac_blocks, lambda r: r.ac_block_id, "AC Block")
    pcs = registry(allocation.pcs_instances, lambda r: r.pcs_id, "PCS")
    ports = registry(allocation.input_ports, lambda r: (r.pcs_id, r.port_id), "PCS input port")
    transformers = registry(
        allocation.transformer_instances, lambda r: r.transformer_id, "transformer"
    )
    windings = registry(
        allocation.lv_windings, lambda r: (r.transformer_id, r.winding_id), "LV winding"
    )
    assignments = registry(allocation.unit_assignments, lambda r: r.unit_id, "unit assignment")

    def exact_coverage(expected: set, actual: set, label: str) -> None:
        missing, extra = sorted(expected - actual), sorted(actual - expected)
        if missing:
            errors.append(f"Missing {label}: {', '.join(missing)}.")
        if extra:
            errors.append(f"Unknown {label}: {', '.join(extra)}.")

    exact_coverage(set(units), set(assignments), "physical unit assignments")
    for assignment in allocation.unit_assignments:
        if assignment.ac_block_id not in ac_blocks:
            errors.append(
                f"Physical unit {assignment.unit_id} references unknown AC Block {assignment.ac_block_id}."
            )
    for item in allocation.pcs_instances:
        if item.ac_block_id not in ac_blocks:
            errors.append(f"PCS {item.pcs_id} references unknown AC Block {item.ac_block_id}.")
        if item.capability_ref is None:
            pending.append(f"PCS {item.pcs_id} capability evidence is missing.")
        else:
            pending.append(f"PCS {item.pcs_id} capability reference is unverified.")
    for item in allocation.transformer_instances:
        if item.ac_block_id not in ac_blocks:
            errors.append(
                f"Transformer {item.transformer_id} references unknown AC Block {item.ac_block_id}."
            )
        if item.capability_ref is None:
            pending.append(f"Transformer {item.transformer_id} capability evidence is missing.")
        else:
            pending.append(f"Transformer {item.transformer_id} capability reference is unverified.")

    dc_bus_owners: dict[str, set[str]] = defaultdict(set)
    for item in allocation.input_ports:
        if item.pcs_id not in pcs:
            errors.append(f"Input port {item.port_id} references unknown PCS {item.pcs_id}.")
        dc_bus_owners[item.dc_bus_id].add(item.pcs_id)
    for bus_id, owners in sorted(dc_bus_owners.items()):
        if len(owners) > 1:
            errors.append(f"DC bus {bus_id} is shared by different PCS: {', '.join(sorted(owners))}.")

    lv_bus_owners: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for item in allocation.lv_windings:
        if item.transformer_id not in transformers:
            errors.append(
                f"LV winding {item.winding_id} references unknown transformer {item.transformer_id}."
            )
        lv_bus_owners[item.lv_bus_id].add((item.transformer_id, item.winding_id))
    for bus_id, owners in sorted(lv_bus_owners.items()):
        if len(owners) > 1:
            errors.append(
                f"LV bus {bus_id} joins different transformer windings; this topology is unsupported."
            )

    domain_counts = Counter(item.domain_id for item in allocation.dc_connections)
    exact_coverage(set(domains), set(domain_counts), "DC domain connections")
    for domain_id, count in sorted(domain_counts.items()):
        if count != 1:
            errors.append(f"DC domain {domain_id} must have exactly one connection; found {count}.")

    pcs_domains: dict[str, set[str]] = defaultdict(set)
    used_ports: set[tuple[str, str]] = set()
    used_dc_pcs: set[str] = set()
    for item in allocation.dc_connections:
        port_key = (item.pcs_id, item.port_id)
        if item.pcs_id not in pcs:
            errors.append(f"DC domain {item.domain_id} references unknown PCS {item.pcs_id}.")
        if port_key not in ports:
            errors.append(
                f"DC domain {item.domain_id} references unknown PCS input port {item.pcs_id}/{item.port_id}."
            )
        domain = domains.get(item.domain_id)
        if domain is None or item.pcs_id not in pcs or port_key not in ports:
            continue
        pcs_domains[item.pcs_id].add(item.domain_id)
        used_ports.add(port_key)
        used_dc_pcs.add(item.pcs_id)
        unit_id = domain.get("unit_id")
        assignment = assignments.get(unit_id) if isinstance(unit_id, str) else None
        if assignment is not None and assignment.ac_block_id != pcs[item.pcs_id].ac_block_id:
            errors.append(
                f"Physical unit {assignment.unit_id} and its domain {item.domain_id} PCS "
                f"{item.pcs_id} must remain in the same AC Block."
            )
    for pcs_id, connected_domains in sorted(pcs_domains.items()):
        if len(connected_domains) > 1:
            suffix = ("is unverified" if pcs[pcs_id].parallel_applicability_ref else "is missing")
            pending.append(
                f"PCS {pcs_id} connects multiple DC domains; parallel applicability evidence {suffix}."
            )

    lv_counts = Counter(item.pcs_id for item in allocation.lv_connections)
    exact_coverage(set(pcs), set(lv_counts), "PCS LV connections")
    for pcs_id, count in sorted(lv_counts.items()):
        if count != 1:
            errors.append(f"PCS {pcs_id} must have exactly one LV connection; found {count}.")

    used_lv_pcs: set[str] = set()
    used_transformers: set[str] = set()
    used_windings: set[tuple[str, str]] = set()
    for item in allocation.lv_connections:
        winding_key = (item.transformer_id, item.winding_id)
        if item.pcs_id not in pcs:
            errors.append(f"LV connection references unknown PCS {item.pcs_id}.")
        if item.transformer_id not in transformers:
            errors.append(f"PCS {item.pcs_id} references unknown transformer {item.transformer_id}.")
        if winding_key not in windings:
            errors.append(
                f"PCS {item.pcs_id} references unknown LV winding {item.transformer_id}/{item.winding_id}."
            )
        if (item.pcs_id not in pcs or item.transformer_id not in transformers
                or winding_key not in windings):
            continue
        if pcs[item.pcs_id].ac_block_id != transformers[item.transformer_id].ac_block_id:
            errors.append(f"PCS {item.pcs_id} and transformer {item.transformer_id} must share an AC Block.")
            continue
        used_lv_pcs.add(item.pcs_id)
        used_transformers.add(item.transformer_id)
        used_windings.add(winding_key)

    for pcs_id in pcs:
        if pcs_id not in used_dc_pcs:
            errors.append(f"Unused PCS {pcs_id}: no valid DC domain connection.")
        if pcs_id not in used_lv_pcs:
            errors.append(f"Unused PCS {pcs_id}: no valid LV connection.")
    for port_key in ports:
        if port_key not in used_ports:
            errors.append(f"Unused PCS input port {port_key[0]}/{port_key[1]}.")
    for transformer_id in transformers:
        if transformer_id not in used_transformers:
            errors.append(f"Unused transformer {transformer_id}.")
    for winding_key in windings:
        if winding_key not in used_windings:
            errors.append(f"Unused LV winding {winding_key[0]}/{winding_key[1]}.")
    used_ac_blocks = {
        pcs[pcs_id].ac_block_id for pcs_id in used_dc_pcs & used_lv_pcs
    }
    for ac_block_id in ac_blocks:
        if ac_block_id not in used_ac_blocks:
            errors.append(f"Unused AC Block {ac_block_id}: no complete declared DC-to-LV path.")

    # Keep diagnostics deterministic and avoid repeated messages from repeated edges.
    errors = list(dict.fromkeys(errors))
    return {
        "topology_valid": not errors,
        "errors": errors,
        "pending_evidence": list(dict.fromkeys(pending)),
    }

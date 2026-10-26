"""Synthetic connectivity tests; these are not CALB equipment capability data."""

import copy

import pytest
from pydantic import ValidationError

from calb_sizing_tool.schemas.dc_ac_allocation import DcAcAllocation
from calb_sizing_tool.services.dc_ac_allocation_topology import validate_allocation_topology


def declared_allocation():
    return {
        "contract_type": "dc_ac_allocation_v1", "schema_version": 1,
        "source": {"dc_manifest_sha256": "a" * 64, "candidate_comparison_sha256": "b" * 64},
        "ac_blocks": [{"ac_block_id": "AC-1"}],
        "pcs_instances": [
            {"pcs_id": "PCS-1", "ac_block_id": "AC-1"},
            {"pcs_id": "PCS-2", "ac_block_id": "AC-1"},
        ],
        "input_ports": [
            {"pcs_id": "PCS-1", "port_id": "P1", "dc_bus_id": "DCBUS-1"},
            {"pcs_id": "PCS-2", "port_id": "P1", "dc_bus_id": "DCBUS-2"},
        ],
        "transformer_instances": [{"transformer_id": "TX-1", "ac_block_id": "AC-1"}],
        "lv_windings": [{"transformer_id": "TX-1", "winding_id": "LV1", "lv_bus_id": "LVBUS-1"}],
        "unit_assignments": [
            {"unit_id": "DC-001", "ac_block_id": "AC-1"},
            {"unit_id": "DC-002", "ac_block_id": "AC-1"},
        ],
        "dc_connections": [
            {"domain_id": "DC-001/D1", "pcs_id": "PCS-1", "port_id": "P1"},
            {"domain_id": "DC-002/D1", "pcs_id": "PCS-2", "port_id": "P1"},
        ],
        "lv_connections": [
            {"pcs_id": "PCS-1", "transformer_id": "TX-1", "winding_id": "LV1"},
            {"pcs_id": "PCS-2", "transformer_id": "TX-1", "winding_id": "LV1"},
        ],
    }


def declared_manifest():
    return {
        "physical_units": [
            {"unit_id": "DC-001", "electrical_domain_ids": ["DC-001/D1"]},
            {"unit_id": "DC-002", "electrical_domain_ids": ["DC-002/D1"]},
        ],
        "electrical_domains": [
            {"domain_id": "DC-001/D1", "unit_id": "DC-001"},
            {"domain_id": "DC-002/D1", "unit_id": "DC-002"},
        ],
    }


def validate(data=None, manifest=None):
    return validate_allocation_topology(
        DcAcAllocation.model_validate(declared_allocation() if data is None else data),
        declared_manifest() if manifest is None else manifest,
    )


def test_complete_declared_topology_preserves_unknown_equipment_approval():
    data, manifest = declared_allocation(), declared_manifest()
    originals = copy.deepcopy((data, manifest))
    result = validate(data, manifest)
    assert result["topology_valid"] is True
    assert result["errors"] == []
    assert any("manufacturer capability evidence" in row for row in result["pending_evidence"])
    assert any("PCS-1 capability evidence is missing" in row for row in result["pending_evidence"])
    assert (data, manifest) == originals


@pytest.mark.parametrize("version", [True, False, 1.0, "1", 2, None])
def test_schema_version_does_not_coerce(version):
    data = declared_allocation()
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        DcAcAllocation.model_validate(data)


@pytest.mark.parametrize("value", [True, 1, None, "", " AC-1", "AC-1 ", "AC-1\n", "AC 1", "AC\\1", "中文", "x" * 97])
def test_stable_ids_are_explicit_strict_ascii_and_never_trimmed(value):
    data = declared_allocation()
    data["ac_blocks"][0]["ac_block_id"] = value
    with pytest.raises(ValidationError):
        DcAcAllocation.model_validate(data)


def test_stable_ids_accept_documented_punctuation_and_maximum_length():
    data = declared_allocation()
    data["ac_blocks"][0]["ac_block_id"] = "A" + "_.:/-0" * 15 + "12345"
    assert len(data["ac_blocks"][0]["ac_block_id"]) == 96
    assert DcAcAllocation.model_validate(data).ac_blocks[0].ac_block_id == data["ac_blocks"][0]["ac_block_id"]


@pytest.mark.parametrize("value", ["a" * 63, "a" * 65, "g" * 64, " " + "a" * 64, "a" * 64 + "\n", 123, True, None])
def test_source_hashes_require_exact_sha256_hex(value):
    data = declared_allocation()
    data["source"]["dc_manifest_sha256"] = value
    with pytest.raises(ValidationError):
        DcAcAllocation.model_validate(data)


@pytest.mark.parametrize("scope", ["root", "source", "pcs", "capability"])
def test_unknown_fields_are_rejected_at_every_contract_layer(scope):
    data = declared_allocation()
    if scope == "root":
        target = data
    elif scope == "source":
        target = data["source"]
    elif scope == "pcs":
        target = data["pcs_instances"][0]
    else:
        data["pcs_instances"][0]["capability_ref"] = capability_reference()
        target = data["pcs_instances"][0]["capability_ref"]
    target["approved"] = True
    with pytest.raises(ValidationError):
        DcAcAllocation.model_validate(data)


def capability_reference():
    return {"package_code": "SYNTHETIC-PCS", "revision": "test only", "sha256": "c" * 64,
            "evidence_ref": "Synthetic test record, not manufacturer evidence"}


@pytest.mark.parametrize("value", ["", " ", "\t\r\n", True, 23])
def test_capability_text_requires_strict_nonblank_strings(value):
    data = declared_allocation()
    data["pcs_instances"][0]["capability_ref"] = capability_reference()
    data["pcs_instances"][0]["capability_ref"]["evidence_ref"] = value
    with pytest.raises(ValidationError):
        DcAcAllocation.model_validate(data)


def test_capability_reference_is_not_treated_as_review_or_approval():
    data = declared_allocation()
    data["pcs_instances"][0]["capability_ref"] = capability_reference()
    data["transformer_instances"][0]["capability_ref"] = capability_reference()
    result = validate(data)
    assert result["topology_valid"]
    assert "PCS PCS-1 capability reference is unverified." in result["pending_evidence"]
    assert "Transformer TX-1 capability reference is unverified." in result["pending_evidence"]


def test_empty_explicit_registries_are_diagnostic_not_schema_coercion():
    data = declared_allocation()
    for key, value in data.items():
        if isinstance(value, list):
            data[key] = []
    result = validate(data)
    assert not result["topology_valid"]
    assert any("Missing physical unit assignments" in row for row in result["errors"])
    assert any("Missing DC domain connections" in row for row in result["errors"])


def test_lists_are_explicit_bounded_and_not_coerced_from_tuples():
    data = declared_allocation()
    data["ac_blocks"] = tuple(data["ac_blocks"])
    with pytest.raises(ValidationError):
        DcAcAllocation.model_validate(data)
    data["ac_blocks"] = [{"ac_block_id": "AC-1"}] * 10_001
    with pytest.raises(ValidationError):
        DcAcAllocation.model_validate(data)
    data["ac_blocks"] = [{"ac_block_id": "AC-1"}] * 10_000
    assert len(DcAcAllocation.model_validate(data).ac_blocks) == 10_000


@pytest.mark.parametrize("registry,label", [
    ("ac_blocks", "Duplicate AC Block"), ("pcs_instances", "Duplicate PCS:"),
    ("input_ports", "Duplicate PCS input port"),
    ("transformer_instances", "Duplicate transformer"),
    ("lv_windings", "Duplicate LV winding"), ("unit_assignments", "Duplicate unit assignment"),
])
def test_all_registry_identities_must_be_unique(registry, label):
    data = declared_allocation()
    data[registry].append(copy.deepcopy(data[registry][0]))
    result = validate(data)
    assert not result["topology_valid"]
    assert any(label in row for row in result["errors"])


@pytest.mark.parametrize("registry", ["unit_assignments", "dc_connections", "lv_connections"])
def test_exact_unit_domain_and_pcs_lv_coverage_rejects_missing_records(registry):
    data = declared_allocation()
    data[registry].pop()
    result = validate(data)
    assert not result["topology_valid"]
    assert any("Missing" in row for row in result["errors"])


@pytest.mark.parametrize("registry,field,unknown", [
    ("unit_assignments", "unit_id", "UNKNOWN-UNIT"),
    ("dc_connections", "domain_id", "UNKNOWN-DOMAIN"),
    ("lv_connections", "pcs_id", "UNKNOWN-PCS"),
])
def test_extra_coverage_identity_is_not_silently_accepted(registry, field, unknown):
    data = declared_allocation()
    row = copy.deepcopy(data[registry][0])
    row[field] = unknown
    data[registry].append(row)
    result = validate(data)
    assert not result["topology_valid"]
    assert any("Unknown" in row and unknown in row for row in result["errors"])


@pytest.mark.parametrize("registry,needle", [
    ("dc_connections", "must have exactly one connection"),
    ("lv_connections", "must have exactly one LV connection"),
])
def test_duplicate_edges_fail_even_when_targets_are_identical(registry, needle):
    data = declared_allocation()
    data[registry].append(copy.deepcopy(data[registry][0]))
    assert any(needle in row for row in validate(data)["errors"])


def test_one_independent_domain_cannot_feed_different_pcs():
    data = declared_allocation()
    data["dc_connections"].append({"domain_id": "DC-001/D1", "pcs_id": "PCS-2", "port_id": "P1"})
    result = validate(data)
    assert not result["topology_valid"]
    assert any("DC domain DC-001/D1 must have exactly one connection; found 2" in row for row in result["errors"])


@pytest.mark.parametrize("registry,field,unknown", [
    ("unit_assignments", "ac_block_id", "AC-UNKNOWN"),
    ("pcs_instances", "ac_block_id", "AC-UNKNOWN"),
    ("transformer_instances", "ac_block_id", "AC-UNKNOWN"),
    ("input_ports", "pcs_id", "PCS-UNKNOWN"),
    ("lv_windings", "transformer_id", "TX-UNKNOWN"),
    ("dc_connections", "pcs_id", "PCS-UNKNOWN"),
    ("dc_connections", "port_id", "PORT-UNKNOWN"),
    ("lv_connections", "transformer_id", "TX-UNKNOWN"),
    ("lv_connections", "winding_id", "WINDING-UNKNOWN"),
])
def test_unknown_references_are_explicit_failures(registry, field, unknown):
    data = declared_allocation()
    data[registry][0][field] = unknown
    result = validate(data)
    assert not result["topology_valid"]
    assert any("unknown" in row.lower() and unknown in row for row in result["errors"])


def test_different_pcs_never_share_a_global_dc_bus_even_with_different_port_names():
    data = declared_allocation()
    data["input_ports"][1]["dc_bus_id"] = "DCBUS-1"
    data["input_ports"][1]["port_id"] = "OTHER-PORT"
    data["dc_connections"][1]["port_id"] = "OTHER-PORT"
    result = validate(data)
    assert not result["topology_valid"]
    assert any("DC bus DCBUS-1 is shared by different PCS" in row for row in result["errors"])


def test_one_container_independent_domains_remain_inside_one_ac_block():
    data, manifest = declared_allocation(), declared_manifest()
    manifest["physical_units"] = [{"unit_id": "DC-001", "electrical_domain_ids": ["DC-001/D1", "DC-001/D2"]}]
    manifest["electrical_domains"][1] = {"domain_id": "DC-001/D2", "unit_id": "DC-001"}
    data["unit_assignments"].pop()
    data["dc_connections"][1]["domain_id"] = "DC-001/D2"
    assert validate(data, manifest)["topology_valid"]
    data["ac_blocks"].append({"ac_block_id": "AC-2"})
    data["pcs_instances"][1]["ac_block_id"] = "AC-2"
    result = validate(data, manifest)
    assert not result["topology_valid"]
    assert any("Physical unit DC-001 and its domain DC-001/D2 PCS PCS-2" in row for row in result["errors"])


def test_pcs_and_transformer_must_share_ac_block():
    data = declared_allocation()
    data["ac_blocks"].append({"ac_block_id": "AC-2"})
    data["transformer_instances"][0]["ac_block_id"] = "AC-2"
    assert any("PCS PCS-1 and transformer TX-1 must share an AC Block" in row for row in validate(data)["errors"])


@pytest.mark.parametrize("second_transformer", [False, True])
def test_shared_lv_bus_cannot_tie_different_windings_or_transformers(second_transformer):
    data = declared_allocation()
    tx_id = "TX-2" if second_transformer else "TX-1"
    if second_transformer:
        data["transformer_instances"].append({"transformer_id": tx_id, "ac_block_id": "AC-1"})
    data["lv_windings"].append({"transformer_id": tx_id, "winding_id": "LV2", "lv_bus_id": "LVBUS-1"})
    data["lv_connections"][1].update(transformer_id=tx_id, winding_id="LV2")
    result = validate(data)
    assert not result["topology_valid"]
    assert any("LV bus LVBUS-1 joins different transformer windings" in row for row in result["errors"])


def test_separate_windings_have_explicit_separate_bus_identities():
    data = declared_allocation()
    data["lv_windings"].append({"transformer_id": "TX-1", "winding_id": "LV2", "lv_bus_id": "LVBUS-2"})
    data["lv_connections"][1]["winding_id"] = "LV2"
    result = validate(data)
    assert result["topology_valid"]
    assert "winding_kva" not in result  # No equal-capacity split is manufactured.


@pytest.mark.parametrize("reference", [None, "SYNTHETIC parallel reference, not approval"])
def test_multiple_domains_to_one_pcs_stays_pending_even_when_reference_is_supplied(reference):
    data = declared_allocation()
    data["pcs_instances"].pop()
    data["pcs_instances"][0]["parallel_applicability_ref"] = reference
    data["input_ports"].pop()
    data["dc_connections"][1]["pcs_id"] = "PCS-1"
    data["lv_connections"].pop()
    result = validate(data)
    assert result["topology_valid"]
    assert any("multiple DC domains; parallel applicability evidence" in row for row in result["pending_evidence"])
    assert any(("is missing" if reference is None else "is unverified") in row
               for row in result["pending_evidence"] if "parallel applicability" in row)


@pytest.mark.parametrize("registry,row,needle", [
    ("pcs_instances", {"pcs_id": "SPARE-PCS", "ac_block_id": "AC-1"}, "Unused PCS SPARE-PCS"),
    ("input_ports", {"pcs_id": "PCS-1", "port_id": "SPARE", "dc_bus_id": "SPARE-BUS"}, "Unused PCS input port PCS-1/SPARE"),
    ("transformer_instances", {"transformer_id": "SPARE-TX", "ac_block_id": "AC-1"}, "Unused transformer SPARE-TX"),
    ("lv_windings", {"transformer_id": "TX-1", "winding_id": "SPARE", "lv_bus_id": "SPARE-LV"}, "Unused LV winding TX-1/SPARE"),
    ("ac_blocks", {"ac_block_id": "SPARE-AC"}, "Unused AC Block SPARE-AC"),
])
def test_unused_registrations_cannot_hide_unconnected_equipment(registry, row, needle):
    data = declared_allocation()
    data[registry].append(row)
    result = validate(data)
    assert not result["topology_valid"]
    assert any(needle in error for error in result["errors"])


@pytest.mark.parametrize("field", ["physical_units", "electrical_domains"])
@pytest.mark.parametrize("value", [None, [], {}, "inferred"])
def test_manifest_requires_explicit_nonempty_unit_and_domain_registers(field, value):
    manifest = declared_manifest()
    manifest[field] = value
    result = validate(manifest=manifest)
    assert not result["topology_valid"]
    assert any(f"Manifest {field} must be a non-empty explicit register" in row for row in result["errors"])


@pytest.mark.parametrize("field", ["physical_units", "electrical_domains"])
def test_manifest_duplicate_identities_are_rejected(field):
    manifest = declared_manifest()
    manifest[field].append(copy.deepcopy(manifest[field][0]))
    result = validate(manifest=manifest)
    assert not result["topology_valid"]
    assert any("Duplicate manifest" in row for row in result["errors"])


@pytest.mark.parametrize("bad_owner", ["UNKNOWN", None, []])
def test_manifest_domain_owner_must_resolve_to_exact_physical_unit(bad_owner):
    manifest = declared_manifest()
    manifest["electrical_domains"][0]["unit_id"] = bad_owner
    result = validate(manifest=manifest)
    assert not result["topology_valid"]
    assert any("references unknown physical unit" in row for row in result["errors"])


@pytest.mark.parametrize("domain_list", [None, [], "D1", [None], [["D1"]], ["DC-002/D1"], ["DC-001/D1", "DC-001/D1"]])
def test_manifest_physical_unit_domains_cannot_be_guessed_or_reassigned(domain_list):
    manifest = declared_manifest()
    manifest["physical_units"][0]["electrical_domain_ids"] = domain_list
    assert not validate(manifest=manifest)["topology_valid"]


def test_diagnostics_are_deterministic_and_inputs_are_not_mutated():
    data = declared_allocation()
    data["dc_connections"].append(copy.deepcopy(data["dc_connections"][0]))
    first = validate(data)
    assert first == validate(data)
    assert len(first["errors"]) == len(set(first["errors"]))

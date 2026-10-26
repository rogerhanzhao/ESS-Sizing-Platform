"""Revalidate an explicitly selected C2b comparison for local mapping diagnostics.

The caller supplies the separately retained comparison digest. A content digest
detects substitution; it is not a manufacturer approval or a release signature.
No sizing formula, catalogue record or adopted run is changed here.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import re

from pydantic import BaseModel

from calb_sizing_tool.services.dc_composition_dispatch_service import assess_proportional_dc_dispatch
from calb_sizing_tool.services.dc_composition_manifest_service import build_dc_composition_manifest
from calb_sizing_tool.services.dc_configuration_variant_service import DcConfigurationVariantService
from calb_sizing_tool.services.dc_product_comparison_service import package_sha256


def comparison_json(comparison: dict) -> dict:
    """Accept in-memory C2b results or their finite JSON download, identically."""
    if not isinstance(comparison, dict):
        raise ValueError('An explicit C2b comparison object is required')
    try:
        payload = {key: value.model_dump(mode='json') if isinstance(value, BaseModel) else deepcopy(value)
                   for key, value in comparison.items()}
        return json.loads(json.dumps(payload, allow_nan=False))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('The comparison must contain finite JSON data') from exc


def _records(value, label, required_text, *, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f'{label} must be an explicit list of records')
    for row in value:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip()
                                            for key in required_text):
            raise ValueError(f'{label} records require explicit text identities')
    return value


def revalidate_allocation_source(revision_service, comparison: dict, expected_comparison_sha256: str,
                                 *, variant_service=None) -> dict:
    """Bind mapping to exact comparison content and re-read current DC reviews.

    C2b curve approval remains the source comparison's evidence boundary. This
    adapter rechecks current product/lineage and declared discharge duty, not
    the lifetime calculation or an equipment capability package.
    """
    if (not isinstance(expected_comparison_sha256, str)
            or not re.fullmatch(r'[0-9a-f]{64}', expected_comparison_sha256)):
        raise ValueError('The separately retained comparison SHA256 is required')
    payload = comparison_json(comparison)
    if (type(payload.get('contract_version')) is not int or payload['contract_version'] != 1
            or payload.get('comparison_only') is not True or payload.get('downstream_ready') is not False):
        raise ValueError('Only the comparison-only C2b version-1 result is supported')
    actual_digest = package_sha256({key: value for key, value in payload.items() if key != 'comparison_sha256'})
    if payload.get('comparison_sha256') != actual_digest or actual_digest != expected_comparison_sha256:
        raise ValueError('The selected C2b comparison digest does not match its content or retained identity')
    manifest = payload.get('manifest')
    if not isinstance(manifest, dict):
        raise ValueError('The source comparison has no explicit DC composition manifest')
    bom = _records(manifest.get('bom'), 'DC composition BOM', ('revision_id', 'role'))
    if any(type(row.get('quantity')) is not int or row['quantity'] <= 0 for row in bom):
        raise ValueError('DC composition BOM quantities must be positive whole numbers')
    units = _records(manifest.get('physical_units'), 'Physical equipment register', ('unit_id', 'revision_id'))
    domains = _records(manifest.get('electrical_domains'), 'Electrical domain register',
                       ('domain_id', 'unit_id', 'revision_id'), nonempty=False)
    evidence = _records(payload.get('evidence'), 'Product evidence register', ('revision_id',))
    stage1 = payload.get('stage1')
    power = stage1.get('dc_power_required_mw') if isinstance(stage1, dict) else None
    try:
        valid_power = (not isinstance(power, bool) and isinstance(power, (int, float))
                       and math.isfinite(power) and power > 0)
    except OverflowError:
        valid_power = False
    if not valid_power:
        raise ValueError('The signed comparison must contain positive finite DC discharge duty')
    variant_service = variant_service or DcConfigurationVariantService(
        revision_service.auth_user, revision_service.db_url)
    details = {row['revision_id']: revision_service.inspect(row['revision_id']) for row in bom}
    scope = manifest.get('scope')
    if (not isinstance(scope, dict) or type(scope.get('allow_special_configurations')) is not bool
            or not isinstance(scope.get('special_reason'), str)):
        raise ValueError('The source comparison configuration scope is incomplete')
    if (len(evidence) != len(details)
            or {row.get('revision_id') for row in evidence} != set(details)):
        raise ValueError('The source comparison must identify every product evidence record exactly once')
    evidence_by_revision = {row['revision_id']: row for row in evidence}
    for revision, detail in details.items():
        if (detail.get('candidate_review_current') is not True or detail.get('stale') is not False
                or detail.get('sha256') != evidence_by_revision[revision].get('revision_sha256')):
            raise ValueError('A source DC product review is no longer current')
        current_scope = variant_service.assert_comparison_scope(revision,
            allow_special_configurations=scope['allow_special_configurations'], special_reason=scope['special_reason'])
        if current_scope != evidence_by_revision[revision].get('configuration_scope'):
            raise ValueError('A source parent-child configuration review has changed')

    # Rebuild with current catalogue evidence. Partitions are explicit source
    # declarations, never inferred from strings, racks or legacy output counts.
    partitions = {}
    for unit in units:
        revision = unit['revision_id']
        if revision not in partitions:
            rows = [{key: value for key, value in row.items()
                     if key not in ('domain_id', 'unit_id', 'revision_id')}
                    for row in domains if row.get('unit_id') == unit['unit_id']]
            if rows:
                partitions[revision] = rows
    rebuilt = build_dc_composition_manifest(revision_service,
        [{key: row[key] for key in ('revision_id', 'quantity', 'role')} for row in bom],
        variant_service=variant_service, allow_special_configurations=scope['allow_special_configurations'],
        special_reason=scope['special_reason'], electrical_partitions=partitions)
    if rebuilt['manifest_sha256'] != manifest.get('manifest_sha256') or rebuilt != manifest:
        raise ValueError('The source DC composition no longer matches the current catalogue and configuration reviews')
    dispatch = assess_proportional_dc_dispatch(manifest, details, dc_power_required_mw=power)
    if dispatch != payload.get('dispatch') or dispatch['status'] != payload.get('dc_duty_status'):
        raise ValueError('The source DC discharge assessment does not match its current physical equipment')
    return dict(comparison=payload, manifest=rebuilt, dispatch=dispatch,
                comparison_sha256=actual_digest, manifest_sha256=rebuilt['manifest_sha256'])

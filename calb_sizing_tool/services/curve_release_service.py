"""Version and adapt engineering input data around the unchanged DC engine."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math

import pandas as pd
from sqlalchemy import select, update

from calb_sizing_tool.infra.db.models import AuditLog, SupplierDegradationImport
from calb_sizing_tool.infra.db.models.curve_release import CurveRelease, CurveDefaultBinding
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.supplier_degradation_library_service import _require_admin
from calb_sizing_tool.services.supplier_degradation_service import parse_supplier_degradation
from calb_sizing_tool.services.master_data_service import MasterDataService
from calb_sizing_tool.services.stage3_service import select_soh_profile
from calb_sizing_tool.config import DC_DATA_PATH

SCOPE = 'CALB-314AH-A'
BASIS_KEY = 'curve_basis_v1'


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def frame_records(frame):
    # Keep full Python float precision; DataFrame.to_json defaults to only
    # ten decimal places and would silently change paired RTE values.
    return frame.astype(object).where(pd.notnull(frame), None).to_dict(orient='records')


def family_key(curve):
    return f"soc{curve['soc_pct']:g}.{curve['basis']}"


def families(payload):
    # A family always retains all ordinary frequency/rate cases; never drop
    # a shorter curve to coerce the original nearest-profile selection.
    keys = sorted({family_key(c) for c in payload['curves']
                   if c['power_rate'] in (.25, .33, .5) and c['cycles_per_day'] <= 2})
    return keys


def _family_curves(payload, key):
    if key not in families(payload):
        raise ValueError('Unknown published operating family.')
    return [c for c in payload['curves'] if family_key(c) == key
            and c['power_rate'] in (.25, .33, .5) and c['cycles_per_day'] <= 2]


def _release_dict(row):
    if digest(row.payload_json) != row.payload_sha256:
        raise ValueError('Curve release checksum mismatch; sizing is blocked.')
    return dict(release_id=row.release_id, version_label=row.version_label,
                status=row.status, payload_sha256=row.payload_sha256,
                payload=deepcopy(row.payload_json), review_note=row.review_note)


class CurveReleaseService:
    def __init__(self, db_url=None):
        self.db_url = db_url

    def list_releases(self):
        with session_scope(self.db_url) as s:
            rows = []
            for r in s.scalars(select(CurveRelease).order_by(CurveRelease.created_at.desc())):
                try:
                    rows.append(_release_dict(r))
                except ValueError:
                    rows.append(dict(release_id=r.release_id, version_label=r.version_label,
                                     status='corrupt', review_note='Checksum mismatch; unavailable for new runs.'))
            return rows

    def get_release(self, release_id):
        with session_scope(self.db_url) as s:
            row = s.get(CurveRelease, release_id)
            if row is None:
                raise ValueError('The selected curve release is unavailable.')
            return _release_dict(row)

    def get_default(self):
        with session_scope(self.db_url) as s:
            row = s.get(CurveDefaultBinding, SCOPE)
            if row is None:
                return None
            release = s.get(CurveRelease, row.release_id)
            if release is None or release.status != 'published':
                raise ValueError('Default curve release is unavailable; no legacy fallback is permitted.')
            _release_dict(release)
            return dict(release_id=row.release_id, family_key=row.family_key,
                        payload_sha256=release.payload_sha256, revision=row.revision)

    def get_binding(self):
        """Admin recovery can replace a corrupt default without using its data."""
        with session_scope(self.db_url) as s:
            row = s.get(CurveDefaultBinding, SCOPE)
            return dict(release_id=row.release_id, family_key=row.family_key,
                        revision=row.revision) if row else None

    def publish(self, import_id, version_label, review_note, actor, *, rte_release_id=None):
        label, note = version_label.strip(), review_note.strip()
        if not label or len(label) > 128 or not note:
            raise ValueError('A version label and an engineering review note are required.')
        # Freeze the explicitly paired RTE version rather than reading live
        # master RTE values on each future run.
        rte_source = self.get_release(rte_release_id) if rte_release_id else None
        if rte_source and (rte_source['status'] != 'published'
                           or rte_source['payload']['scope_cell_code'] != SCOPE):
            raise ValueError('Select an applicable published RTE version.')
        if rte_source:
            rp = pd.DataFrame(rte_source['payload']['rte_profiles'])
            rc = pd.DataFrame(rte_source['payload']['rte_bands'])
        else:
            dfs = MasterDataService(self.db_url).build_soh_rte_dataframes()
            rp, rc = dfs['df_rte_profile'], dfs['df_rte_curve']
            if rp is None or rc is None:
                raise ValueError('Existing approved RTE data are required for explicit pairing.')
        with session_scope(self.db_url) as s:
            _require_admin(s, actor)
            row = s.get(SupplierDegradationImport, import_id)
            if row is None:
                raise ValueError('Candidate source not found.')
            if hashlib.sha256(row.source_bytes).hexdigest() != row.source_sha256:
                raise ValueError('Candidate source checksum mismatch.')
            parsed = json.loads(json.dumps(asdict(parse_supplier_degradation(row.source_bytes))))
            if parsed != row.dataset_json:
                raise ValueError('Candidate values differ from original source.')
            if any(c['issues'] for c in parsed['curves']):
                raise ValueError('Resolve source curve issues before publication.')
            payload = dict(schema_version=1, source_sha256=row.source_sha256,
                           source_version=row.version_label, scope_cell_code=SCOPE,
                           curves=parsed['curves'], rte_version='paired-legacy-rte-v1',
                           rte_profiles=frame_records(rp),
                           rte_bands=frame_records(rc))
            payload['reference_workbook_sha256'] = hashlib.sha256(DC_DATA_PATH.read_bytes()).hexdigest()
            if rte_source:
                for key in ('rte_profiles','rte_bands','rte_version'):
                    payload[key] = deepcopy(rte_source['payload'][key])
                if rte_source['payload'].get('rte_rule'):
                    payload['rte_rule'] = deepcopy(rte_source['payload']['rte_rule'])
                payload['rte_source_release_id'] = rte_source['release_id']
            if not families(payload):
                raise ValueError('Source contains no supported ordinary operating families.')
            release = CurveRelease(version_label=label, source_import_id=import_id,
                                   status='published', payload_json=payload, payload_sha256=digest(payload),
                                   review_note=note, actor=actor)
            s.add(release)
            s.flush()
            s.add(AuditLog(entity_type='curve_release', entity_id=release.release_id,
                           action='publish', actor=actor, payload_json=dict(version=label, sha256=release.payload_sha256, review_note=note)))
            return _release_dict(release)

    def set_default(self, release_id, key, actor, expected_revision):
        with session_scope(self.db_url) as s:
            if s.get_bind().dialect.name == 'sqlite':
                s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            _require_admin(s, actor)
            row = s.get(CurveRelease, release_id)
            if row is None or row.status != 'published':
                raise ValueError('Only a published release can be the default.')
            release = _release_dict(row)
            _family_curves(release['payload'], key)
            current = s.get(CurveDefaultBinding, SCOPE)
            revision = current.revision if current else 0
            if expected_revision != revision:
                raise ValueError('Default changed during review. Refresh before applying.')
            if current:
                result = s.execute(update(CurveDefaultBinding).where(
                    CurveDefaultBinding.scope_key == SCOPE,
                    CurveDefaultBinding.revision == expected_revision).values(
                    release_id=release_id, family_key=key, revision=revision+1))
                if result.rowcount != 1:
                    raise ValueError('Concurrent default update; refresh before applying.')
            else:
                s.add(CurveDefaultBinding(scope_key=SCOPE, release_id=release_id,
                                         family_key=key, revision=1))
            s.add(AuditLog(entity_type='curve_default_binding', entity_id=SCOPE, action='set_default', actor=actor,
                           payload_json=dict(release_id=release_id, family_key=key, previous_revision=revision)))

    def retire(self, release_id, actor):
        with session_scope(self.db_url) as s:
            if s.get_bind().dialect.name == 'sqlite':
                s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            _require_admin(s, actor)
            if s.scalar(select(CurveDefaultBinding).where(CurveDefaultBinding.release_id == release_id)):
                raise ValueError('Switch the default before retiring this release.')
            row = s.get(CurveRelease, release_id)
            if row is None:
                raise ValueError('Release not found.')
            row.status = 'retired'
            s.add(AuditLog(entity_type='curve_release', entity_id=release_id,
                           action='retire', actor=actor, payload_json={}))

    def prepare(self, bundle, selection, *, life_years, cycles_per_year, verify_reference=False):
        selection = deepcopy(selection) if selection else self.get_default()
        if not selection:
            return bundle, None
        if not all(isinstance(selection.get(k), str) and selection[k]
                   for k in ('release_id','family_key','payload_sha256')):
            raise ValueError('Incomplete versioned curve selection; choose a published operating family.')
        release = self.get_release(selection['release_id'])
        if release['status'] != 'published':
            raise ValueError('This release is retired; choose a published version for a new run.')
        if selection.get('payload_sha256') != release['payload_sha256']:
            raise ValueError('The selected release hash changed; reload the curve selection.')
        payload = release['payload']
        if verify_reference and (not payload.get('reference_workbook_sha256')
                or hashlib.sha256(bundle.workbook_path.read_bytes()).hexdigest() != payload['reference_workbook_sha256']):
            raise ValueError('The reference workbook differs from the approved product basis. Review its product/cell applicability before using this release.')
        curves = _family_curves(payload, selection['family_key'])
        max_cycles = max(c['cycles_per_day']*365. for c in curves)
        if cycles_per_year > max_cycles:
            raise ValueError(f'Requested {cycles_per_year:g} cycles/year exceeds this published family maximum ({max_cycles:g}). Choose an approved extended-duty version; no lighter-duty substitution is permitted.')
        profiles, points = [], []
        for i, c in enumerate(curves, 1):
            profiles.append(dict(Profile_Id=i, C_Rate=c['power_rate'], Cycles_Per_Year=c['cycles_per_day']*365.0))
            points += [dict(Profile_Id=i, Life_Year_Index=y, Soh_Dc_Pct=v/100.)
                       for y, v in zip(c['years'], c['retention_pct']) if v is not None]
        sp, sc = pd.DataFrame(profiles), pd.DataFrame(points)
        # For a rectangular ordinary grid, at every rate the nearest frequency
        # has identical frequency score. Check all possible rate selections.
        for rate in sorted(set(sp.C_Rate)):
            profile_id, _, _ = select_soh_profile(rate, cycles_per_year, sp)
            _check_years(sc, profile_id, life_years)
        frames = dict(df_soh_profile=sp, df_soh_curve=sc,
                      df_rte_profile=pd.DataFrame(payload['rte_profiles']),
                      df_rte_curve=pd.DataFrame(payload['rte_bands']))
        basis = dict(schema_version=1, release_id=release['release_id'], version_label=release['version_label'],
                     payload_sha256=release['payload_sha256'], family_key=selection['family_key'],
                     source_sha256=payload['source_sha256'], scope_cell_code=payload['scope_cell_code'],
                     reference_workbook_sha256=payload.get('reference_workbook_sha256'),
                     rte_version=payload['rte_version'], selection_mode=selection.get('selection_mode', 'default'),
                     rte_rule=deepcopy(payload.get('rte_rule')),
                     source_soc_pct=curves[0]['soc_pct'], source_series=curves[0]['basis'],
                     curves=deepcopy(curves), requested_cycles_per_year=cycles_per_year,
                     input_package={k:frame_records(v) for k,v in frames.items()})
        basis['package_sha256'] = digest(basis['input_package'])
        return bundle.model_copy(update=frames), basis


def _check_years(frame, profile_id, life_years):
    values = frame[frame.Profile_Id == profile_id].set_index('Life_Year_Index').Soh_Dc_Pct.to_dict()
    if any(y not in values or not math.isfinite(values[y]) or not 0 < values[y] <= 1
           for y in range(int(life_years)+1)):
        raise ValueError(f'Source SOH profile {profile_id} does not support the full {life_years}-year life. No extrapolation or lighter-duty substitution is permitted.')


def attach_curve_basis(snapshot, basis):
    if basis is None:
        return snapshot
    basis = deepcopy(basis)
    if digest(basis['input_package']) != basis['package_sha256']:
        raise ValueError('Runtime curve package checksum mismatch.')
    meta = snapshot.stage3.meta
    frame = pd.DataFrame(basis['input_package']['df_soh_curve'])
    _check_years(frame, meta.soh_profile_id, snapshot.stage1.project_life_years)
    profile = next(p for p in basis['input_package']['df_soh_profile'] if p['Profile_Id']==meta.soh_profile_id)
    if profile['C_Rate'] != meta.chosen_soh_c_rate or int(profile['Cycles_Per_Year']) != meta.chosen_soh_cycles_per_year:
        raise ValueError('Calculated profile metadata do not match the frozen curve package.')
    source_values = frame[frame.Profile_Id==meta.soh_profile_id].set_index('Life_Year_Index').Soh_Dc_Pct.to_dict()
    for row in snapshot.stage3.rows:
        # Read-back check of the existing engine's documented SOH rounding,
        # not a second energy or sizing calculation.
        expected = round(source_values[row.year_index]*100., 1)/100.
        if not math.isclose(row.soh_relative, expected, abs_tol=1e-12, rel_tol=0):
            raise ValueError('Calculated SOH points differ from the frozen source curve.')
    if meta.effective_c_rate > max(p['C_Rate'] for p in basis['input_package']['df_soh_profile']) + 1e-9:
        raise ValueError('Effective C-rate exceeds the published family maximum; select an applicable data basis.')
    basis.update(selected_profile_id=meta.soh_profile_id, source_rate=profile['C_Rate'],
                 source_cycles_per_year=profile['Cycles_Per_Year'], source_cycles_per_day=profile['Cycles_Per_Year']/365.,
                 selected_rte_profile_id=meta.rte_profile_id)
    rte_frame=pd.DataFrame(basis['input_package']['df_rte_curve'])
    positive=rte_frame[(rte_frame.Profile_Id==meta.rte_profile_id) & (rte_frame.Soh_Band_Min_Pct>0)].Soh_Band_Min_Pct
    basis['rte_low_soh_fallback_used']=bool(not positive.empty and any(source_values[r.year_index]<positive.min() for r in snapshot.stage3.rows))
    result = snapshot.model_copy(deep=True)
    result.summary[BASIS_KEY] = basis
    return result


def validate_snapshot_basis(snapshot, selection):
    basis = snapshot.summary.get(BASIS_KEY)
    if selection and not basis:
        raise ValueError('A versioned curve selection requires the actual run curve package.')
    if not basis:
        return
    if not selection or any(selection.get(k) != basis.get(k) for k in ('release_id','family_key','payload_sha256')):
        raise ValueError('Saved curve selection differs from the calculated result.')
    if digest(basis['input_package']) != basis['package_sha256']:
        raise ValueError('Saved runtime curve package checksum mismatch.')
    checked = attach_curve_basis(snapshot, basis).summary[BASIS_KEY]
    if any(checked.get(k) != basis.get(k) for k in ('selected_profile_id','source_rate','source_cycles_per_year','selected_rte_profile_id')):
        raise ValueError('Saved selected profile differs from the calculated result.')


def curve_display_meta(snapshot):
    """Enrich presentation dictionaries only, preserving frozen Stage3Meta."""
    meta = snapshot.stage3.meta.to_legacy_dict()
    basis = snapshot.summary.get(BASIS_KEY)
    if basis:
        meta['chosen_soh_cycles_per_year'] = basis['source_cycles_per_year']
        meta[BASIS_KEY] = {k:v for k,v in basis.items() if k not in ('input_package','curves')}
    return meta

"""Old-workbook RTE rule and editable review versions, outside sizing stages."""
from __future__ import annotations
from copy import deepcopy
import math

import pandas as pd
from sqlalchemy import select

from calb_sizing_tool.infra.db.models import AuditLog
from calb_sizing_tool.infra.db.models.curve_release import CurveRelease
from calb_sizing_tool.infra.db.models.curve_release_draft import CurveReleaseDraft
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.curve_release_service import CurveReleaseService, digest, _family_curves
from calb_sizing_tool.services.supplier_degradation_library_service import _require_admin
from calb_sizing_tool.services.stage3_service import select_rte_profile


def _curve_rows(payload):
    rates = {p['Profile_Id']:p['C_Rate'] for p in payload['rte_profiles']}
    return [dict(row=i,profile_id=r['Profile_Id'],rate=rates[r['Profile_Id']],
                 soh_min_pct=r['Soh_Band_Min_Pct']*100.,rte_pct=r['Rte_Dc_Pct']*100.)
            for i,r in enumerate(payload['rte_bands'])]


def derive_legacy_rte(payload):
    """Reproduce every stored old 0.5C band, without inventing an aging fit.

    Workbook rte_profile_314_data!F4 documents k=1.6, eps_pp=0.02.
    Its 19 validation rows reproduce exactly B-1.6*(B-C). The epsilon
    activation branch is absent from the saved workbook, so no unverified
    epsilon formula is introduced; the existing rows all exceed that gap.
    """
    result=deepcopy(payload)
    profiles={p['C_Rate']:p['Profile_Id'] for p in result['rte_profiles']}
    if not all(rate in profiles for rate in (.25,.33,.5)):
        raise ValueError('Legacy RTE generation requires 0.25C, 0.33C and 0.5C profiles.')
    groups={rate:[r for r in result['rte_bands'] if r['Profile_Id']==profiles[rate]] for rate in profiles}
    if not (len(groups[.25])==len(groups[.33])==len(groups[.5])):
        raise ValueError('The legacy rate band grids do not align.')
    for a,b,c in zip(groups[.25],groups[.33],groups[.5]):
        if not a['Soh_Band_Min_Pct']==b['Soh_Band_Min_Pct']==c['Soh_Band_Min_Pct']:
            raise ValueError('The legacy SOH band thresholds do not align.')
        c['Rte_Dc_Pct']=a['Rte_Dc_Pct']-1.6*(a['Rte_Dc_Pct']-b['Rte_Dc_Pct'])
    result['rte_rule']=dict(model='legacy_delta_scaling',k=1.6,source_note_eps_pp=.02,
        formula='RTE_0.5C = RTE_0.25C - 1.6 * (RTE_0.25C - RTE_0.33C)',
        source='rte_profile_314_data!F4; rte_314_validation!B2:E20',
        mapping='Existing Stage3 SOH-band lookup; existing monotonic and adjustment controls remain authoritative.',
        source_limit='Old workbook stores numeric values, not executable formulas. Epsilon branch is unverified. Zero-threshold imported tail rows originate from unlabeled source SOH bands; preserved as legacy fallback, not new test evidence.')
    result['rte_version']='legacy-rule-1p6-'+digest(result['rte_bands'])[:12]
    _validate_rows(_curve_rows(result),_curve_rows(result))
    return result


def _validate_rows(rows,expected):
    if len(rows)!=len(expected):
        raise ValueError('Keep the complete existing RTE band grid.')
    for row,old in zip(rows,expected):
        if any(row.get(k)!=old.get(k) for k in ('row','profile_id','rate','soh_min_pct')):
            raise ValueError('Rate and SOH thresholds are fixed; edit only RTE percentages.')
        value=row.get('rte_pct')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=100:
            raise ValueError('RTE must be a finite percentage greater than zero and at most 100.')
    # Check rate ordering at aligned source rows; keep the old raw annual
    # monotonic behavior under the existing Stage3 toggle, not a new formula.
    groups={rate:[r for r in rows if r['rate']==rate] for rate in (.25,.33,.5)}
    for a,b,c in zip(groups[.25],groups[.33],groups[.5]):
        if not a['rte_pct']>=b['rte_pct']>=c['rte_pct']:
            raise ValueError('RTE ordering must satisfy 0.25C >= 0.33C >= 0.5C for each source band.')


def edited_rte_payload(base_payload,rows,note):
    payload=derive_legacy_rte(base_payload)
    generated=_curve_rows(payload)
    _validate_rows(rows,generated)
    manual=False
    for row,original,band in zip(rows,generated,payload['rte_bands']):
        if abs(row['rte_pct']-original['rte_pct'])>1e-10:
            band['Rte_Dc_Pct']=row['rte_pct']/100.
            manual=True
    payload['rte_rule']['manual_override']=manual
    payload['rte_rule']['review_note']=note
    payload['rte_rule']['base_release_sha256']=digest(base_payload)
    payload['rte_version']=('manual-rte-' if manual else 'legacy-rule-1p6-')+digest(payload['rte_bands'])[:12]
    return payload


def annual_rte_preview(payload,key,*,monotonic=True):
    """Read-only matching preview; actual reports consume actual run outputs."""
    rows=[]
    profiles=pd.DataFrame(payload['rte_profiles'])
    for curve in _family_curves(payload,key):
        pid,_=select_rte_profile(curve['power_rate'],profiles)
        bands=pd.DataFrame([r for r in payload['rte_bands'] if r['Profile_Id']==pid]).sort_values('Soh_Band_Min_Pct',ascending=False)
        if monotonic:bands['Rte_Dc_Pct']=bands['Rte_Dc_Pct'].ffill().bfill().cummin()
        positive=bands[bands.Soh_Band_Min_Pct>0].Soh_Band_Min_Pct
        for y,v in zip(curve['years'],curve['retention_pct']):
            if v is None:continue
            selected=bands[bands.Soh_Band_Min_Pct<=v/100.].head(1)
            if selected.empty:selected=bands.tail(1)
            rows.append(dict(rate=curve['power_rate'],cycles_day=curve['cycles_per_day'],year=y,
                             soh_pct=v,dc_rte_pct=float(selected.Rte_Dc_Pct.iloc[0])*100.,
                             legacy_low_soh_fallback=bool(not positive.empty and v/100.<positive.min())))
    return rows


class RteReviewService:
    def __init__(self,db_url=None):self.db_url=db_url

    def list_drafts(self,actor):
        with session_scope(self.db_url) as s:
            _require_admin(s,actor)
            return [dict(draft_id=r.draft_id,version_label=r.version_label,status=r.status,
                         payload=deepcopy(r.payload_json),sha256=r.payload_sha256,
                         base_release_id=r.base_release_id,review_note=r.review_note)
                    for r in s.scalars(select(CurveReleaseDraft).order_by(CurveReleaseDraft.created_at.desc()))]

    def save_draft(self,base_release_id,version_label,rows,note,actor,*,draft_id=None,expected_sha=None,matrix_config=None):
        label,note=version_label.strip(),note.strip()
        if not label or len(label)>128 or not note:
            raise ValueError('A new version label and an edit/review reason are required.')
        with session_scope(self.db_url) as s:
            if s.get_bind().dialect.name=='sqlite':s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            _require_admin(s,actor)
            base=s.get(CurveRelease,base_release_id)
            if base is None or digest(base.payload_json)!=base.payload_sha256:
                raise ValueError('Base release is missing or corrupt.')
            if matrix_config is not None:
                from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package
                payload=build_screenshot_package(base.payload_json,matrix_config.get('test_anchors',[]))
                if rows!=_curve_rows(payload):
                    raise ValueError('Screenshot table differs from the saved test inputs and calculation model.')
                payload['rte_rule']['review_note']=note
            else:
                payload=edited_rte_payload(base.payload_json,rows,note)
            # The review token must cover a name-only edit as well as numeric
            # changes. Keep the numerical RTE version independent of this label.
            payload['rte_rule']['reviewed_version_label']=label
            manual=payload['rte_rule']['manual_override']
            if draft_id:
                draft=s.get(CurveReleaseDraft,draft_id)
                if draft is None or draft.status!='draft' or draft.base_release_id!=base_release_id:
                    raise ValueError('Only an unpublished working draft can be edited.')
                if draft.payload_sha256!=expected_sha:
                    raise ValueError('Draft changed during review; reload before saving.')
            else:
                draft=CurveReleaseDraft(base_release_id=base_release_id,status='draft');s.add(draft)
            draft.version_label=label;draft.review_note=note;draft.actor=actor
            draft.payload_json=payload;draft.payload_sha256=digest(payload)
            s.flush()
            s.add(AuditLog(entity_type='curve_release_draft',entity_id=draft.draft_id,
                           action='save_rte_draft',actor=actor,payload_json=dict(sha256=draft.payload_sha256,manual_override=manual)))
            return draft.draft_id

    def publish_draft(self,draft_id,actor,expected_sha):
        with session_scope(self.db_url) as s:
            if s.get_bind().dialect.name=='sqlite':s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            _require_admin(s,actor)
            draft=s.get(CurveReleaseDraft,draft_id)
            if draft is None or draft.status!='draft':raise ValueError('Only an unpublished saved draft can be published.')
            if draft.payload_sha256!=expected_sha or digest(draft.payload_json)!=expected_sha:
                raise ValueError('Draft changed or failed its checksum; reopen before publication.')
            rule=draft.payload_json.get('rte_rule') or {}
            if 'reviewed_version_label' in rule and rule['reviewed_version_label']!=draft.version_label:
                raise ValueError('Draft version label differs from the reviewed content; reopen and save before publication.')
            base=s.get(CurveRelease,draft.base_release_id)
            if base is None or digest(base.payload_json)!=base.payload_sha256:
                raise ValueError('Base release is missing or corrupt.')
            if (draft.payload_json.get('rte_rule') or {}).get('model')=='screenshot_5pct':
                from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package
                expected=build_screenshot_package(base.payload_json,draft.payload_json['rte_rule']['test_anchors'])
                if expected['rte_bands']!=draft.payload_json['rte_bands']:
                    raise ValueError('Saved screenshot RTE values differ from their calculation inputs.')
                _validate_rows(_curve_rows(draft.payload_json),_curve_rows(expected))
            else:
                _validate_rows(_curve_rows(draft.payload_json),_curve_rows(derive_legacy_rte(base.payload_json)))
            allowed={'rte_bands','rte_rule','rte_version'}
            if ({k:v for k,v in draft.payload_json.items() if k not in allowed}
                    != {k:v for k,v in base.payload_json.items() if k not in allowed}):
                raise ValueError('RTE editing must not modify SOH, product scope or other source metadata.')
            release=CurveRelease(version_label=draft.version_label,source_import_id=base.source_import_id,
                                 status='published',payload_json=deepcopy(draft.payload_json),
                                 payload_sha256=draft.payload_sha256,review_note=draft.review_note,actor=actor)
            s.add(release);s.flush();draft.status='published';draft.published_release_id=release.release_id
            s.add(AuditLog(entity_type='curve_release',entity_id=release.release_id,action='publish_rte_draft',actor=actor,
                           payload_json=dict(draft_id=draft_id,sha256=release.payload_sha256)))
            return release.release_id

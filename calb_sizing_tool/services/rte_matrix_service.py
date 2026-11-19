"""Screenshot-style RTE data preparation; the sizing engine is unchanged."""
from bisect import bisect_left
from copy import deepcopy
import math
import pandas as pd

from calb_sizing_tool.services.curve_release_service import digest
from calb_sizing_tool.services.rte_review_service import derive_legacy_rte, _validate_rows, _curve_rows

NODES = (100,95,90,85,80,75,70,65,60)
RATES = (.25,.33,.5)


def build_screenshot_package(base,anchors=()):
    """Generate constant 5% SOH bins and retain a labeled legacy fallback.

    Tests are inputs, not synthetic measurements. Between measured nodes use
    linear interpolation. Outside them preserve the old model loss shape by
    the nearest-anchor offset; label this modeled calibration explicitly.
    """
    reference=deepcopy(base)
    old_rule=base.get('rte_rule') or {}
    if old_rule.get('legacy_reference_bands'):
        reference['rte_bands']=deepcopy(old_rule['legacy_reference_bands'])
    legacy=derive_legacy_rte(reference)
    ids={p['C_Rate']:p['Profile_Id'] for p in legacy['rte_profiles']}
    seed={};fallback={}
    for rate in RATES:
        bands=pd.DataFrame([r for r in legacy['rte_bands'] if r['Profile_Id']==ids[rate]]).sort_values('Soh_Band_Min_Pct',ascending=False)
        bands['Rte_Dc_Pct']=bands['Rte_Dc_Pct'].cummin()
        def value(h):
            selected=bands[bands.Soh_Band_Min_Pct<=h].head(1)
            return float((selected if not selected.empty else bands.tail(1)).Rte_Dc_Pct.iloc[0])*100.
        seed[rate]={}
        for i,h in enumerate(NODES):
            if h==100:points=[1.]
            else:
                lo,hi=h/100.,NODES[i-1]/100.
                points=[lo,math.nextafter(hi,lo)]
                points += [float(t) for t in bands.Soh_Band_Min_Pct if lo<=t<hi]
            seed[rate][h]=min(value(point) for point in points)
        fallback[rate]=value(0.)
    clean=[];seen=set()
    for a in anchors:
        rate,h,v=a.get('rate'),a.get('soh_pct'),a.get('rte_pct')
        kind=a.get('source_kind','test')
        if (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)
                or not 0<v<=100 or rate not in RATES or h not in NODES or kind not in ('test','engineering_override')):
            raise ValueError('Inputs require a listed rate, a screenshot SOH node (60–100%), and RTE in (0,100].')
        if (rate,h) in seen:raise ValueError('Duplicate rate / SOH input; keep one authoritative value per node.')
        seen.add((rate,h));clean.append(dict(rate=rate,soh_pct=h,rte_pct=v,source_kind=kind))
    values={};origins={};explain=[]
    for rate in RATES:
        points=sorted([a for a in clean if a['rate']==rate],key=lambda a:a['soh_pct'])
        xs=[a['soh_pct'] for a in points]
        values[rate]={};origins[rate]={}
        for h in NODES:
            exact=next((a for a in points if a['soh_pct']==h),None)
            if exact:
                value=exact['rte_pct'];origin=exact['source_kind'];formula='Input retained without modification'
            elif len(points)>=2 and xs[0]<h<xs[-1]:
                i=bisect_left(xs,h);lo,hi=points[i-1],points[i]
                value=lo['rte_pct']+(hi['rte_pct']-lo['rte_pct'])*(h-lo['soh_pct'])/(hi['soh_pct']-lo['soh_pct'])
                origin='interpolated';formula=f"{lo['rte_pct']:g} + ({hi['rte_pct']:g} - {lo['rte_pct']:g}) * ({h:g} - {lo['soh_pct']:g}) / ({hi['soh_pct']:g} - {lo['soh_pct']:g})"
            elif points:
                nearest=min(points,key=lambda a:abs(a['soh_pct']-h))
                delta=nearest['rte_pct']-seed[rate][nearest['soh_pct']]
                value=seed[rate][h]+delta;origin='legacy_model_calibrated'
                formula=f"Old model at H={h:g}% ({seed[rate][h]:.10g}%) + input-minus-old offset ({delta:.10g} pp)"
            else:
                value=seed[rate][h];origin='legacy_model'
                formula='Minimum old applied RTE within this SOH interval; BOL is separate'
            values[rate][h]=value;origins[rate][h]=origin
            explain.append(dict(rate=rate,soh_pct=h,rte_pct=value,origin=origin,calculation=formula))
    # Use the verified cross-rate rule only when no 0.5-rate input is supplied.
    if not any(a['rate']==.5 for a in clean) and any(a['rate'] in (.25,.33) for a in clean):
        for h in NODES:
            values[.5][h]=values[.25][h]-1.6*(values[.25][h]-values[.33][h])
            for row in explain:
                if row['rate']==.5 and row['soh_pct']==h:
                    row.update(rte_pct=values[.5][h],origin='rate_derived',calculation='RTE0.25 - 1.6 * (RTE0.25 - RTE0.33); modeled, not measured')
    payload=deepcopy(base);payload['rte_bands']=[]
    for rate in RATES:
        for h in NODES:
            payload['rte_bands'].append(dict(Profile_Id=ids[rate],Soh_Band_Min_Pct=h/100.,Rte_Dc_Pct=values[rate][h]/100.))
        delta=values[rate][60]-seed[rate][60]
        low=fallback[rate]+delta
        payload['rte_bands'].append(dict(Profile_Id=ids[rate],Soh_Band_Min_Pct=0.,Rte_Dc_Pct=low/100.))
        explain.append(dict(rate=rate,soh_pct=0,rte_pct=low,origin='legacy_low_soh_fallback',calculation='Inherited low-SOH fallback plus H60 calibration offset; not supplier test evidence'))
        chain=[values[rate][h] for h in NODES]+[low]
        if any(b>a+1e-10 for a,b in zip(chain,chain[1:])):
            raise ValueError('Inputs produce RTE increasing as SOH declines. Review the test inputs/model instead of silently changing them.')
    rows=_curve_rows(payload);_validate_rows(rows,rows)
    payload['rte_rule']=dict(model='screenshot_5pct',test_anchors=clean,k=1.6,manual_override=bool(clean),
        source_limit='Values not marked test are modeled. Below60% uses an explicit inherited fallback. No supplier guarantee is inferred.',
        matching='H=100 is BOL; otherwise lower-inclusive / upper-exclusive five-percent SOH intervals.',
        preparation='Old model interval minimum; exact test inputs; linear interpolation between inputs; nearest-input offset on the old model outside test coverage.',
        legacy_reference_bands=deepcopy(reference['rte_bands']),calculation_rows=explain)
    payload['rte_version']='soh5pct-'+digest(payload['rte_bands'])[:12]
    return payload


def matrix_rows(payload):
    explain=payload['rte_rule']['calculation_rows']
    rows=[]
    for i,h in enumerate(NODES):
        label='100% (BOL)' if h==100 else f'{h}% ≤ H < {NODES[i-1]}%'
        rows.append({'SOH interval':label,**{f'{rate:g}P RTE (%)':next(r['rte_pct'] for r in explain if r['rate']==rate and r['soh_pct']==h) for rate in (.5,.33,.25)}})
    return rows

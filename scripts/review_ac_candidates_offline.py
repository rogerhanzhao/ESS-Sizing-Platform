"""Design-only AC candidate review; no database, UI or production writes.

Run from repository root: python -m scripts.review_ac_candidates_offline
All equipment combinations remain simplified concepts, never verified products.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from calb_sizing_tool.services.ac_sizing_service import (
    build_dc_allocation_plan,
    build_simplified_ac_block_models,
    dc_grouping_has_feeder_capacity,
    evaluate_ac_sizing_feasibility,
    generate_ac_sizing_options,
)


def enumerate_case(count: int, unit_mwh: float, target_mw: float, target_mwh: float,
                   outputs: int = 2) -> list[dict]:
    if count <= 0 or unit_mwh <= 0 or target_mw <= 0 or target_mwh <= 0:
        raise ValueError("Review inputs must be positive")
    if outputs not in (1, 2):
        raise ValueError("Only existing one/two-output concepts are supported")
    candidates = []
    for option in generate_ac_sizing_options(count, target_mw, target_mwh, unit_mwh):
        for model in build_simplified_ac_block_models(
            option.pcs_recommendations, grouping_ratio=option.ratio
        ):
            capacity = dc_grouping_has_feeder_capacity(
                option.dc_blocks_per_ac, model.pcs_count,
                dc_block_output_circuits=outputs,
            )
            plan = build_dc_allocation_plan(
                count, option.ac_block_count, model.pcs_count,
                dc_block_output_circuits=outputs,
            ) if capacity else []
            power = option.ac_block_count * model.block_size_mw
            errors, warnings = evaluate_ac_sizing_feasibility(
                total_energy_mwh=count * unit_mwh, target_energy_mwh=target_mwh,
                total_ac_mw=power, target_power_mw=target_mw,
            )
            # Review labels only: do not amend the frozen feasibility function.
            if not capacity:
                status = "回路不足，排除"
            elif errors:
                status = "现有检查报错"
            elif power < target_mw:
                status = "未报错，但装机未达需求"
            else:
                status = "算术可比较；设备及POI能力待确认"
            candidates.append(dict(
                ratio=option.ratio, blocks=option.ac_block_count,
                dc_distribution=option.dc_blocks_per_ac,
                pcs_per_block=model.pcs_count, pcs_kw=model.pcs_kw,
                station_nameplate_mw=power, delta_mw=power-target_mw,
                legacy_preferred=option.is_recommended,
                simplified_ac_enclosure=model.container_type,
                feeder_capacity=capacity, allocation_plan=plan,
                legacy_errors=errors, legacy_warnings=warnings, status=status,
                product_verified=False, poi_deliverable_mw=None,
            ))
    return candidates


def verify() -> None:
    # A three-box, two-AC-block scheme has [2,1]. The larger group's outputs
    # cannot compensate for insufficient outputs in the smaller group.
    tail = enumerate_case(3, 5.015, 8, 12)
    rejected = [c for c in tail if c['ratio'] == '1:2' and c['pcs_per_block'] == 4]
    assert rejected and all(not c['feeder_capacity'] for c in rejected)
    rows = enumerate_case(10, 5.015, 10, 40)
    assert all(c['dc_distribution'] == [4,3,3] for c in rows if c['ratio']=='1:4')
    assert all(c['dc_distribution'] == [5,5] for c in rows if c['ratio']=='1:8')
    for c in rows:
        assert sum(c['dc_distribution']) == 10
        if c['feeder_capacity']:
            assert sum(b['dc_blocks_total'] for b in c['allocation_plan']) == 10
            for block in c['allocation_plan']:
                connections = block['dc_block_connections']
                assert len(connections) == block['dc_blocks_total']
                assert len({x['dc_block_index'] for x in connections}) == len(connections)
                covered = {f for x in connections for f in x['feeder_indices']}
                assert covered == set(range(1,c['pcs_per_block']+1))
                assert all(len(x['feeder_indices']) <= 2 for x in connections)
    gap = enumerate_case(8, 5.015, 10.4, 35)
    assert any(c['status']=='未报错，但装机未达需求' for c in gap)
    assert all(c['poi_deliverable_mw'] is None and not c['product_verified'] for c in gap)


def main() -> None:
    verify()
    cases = [
        dict(name='8箱：比较相同装机功率的不同组织方式',count=8,unit_mwh=5.015,target_mw=10,target_mwh=35),
        dict(name='10箱：核对均衡尾组',count=10,unit_mwh=5.015,target_mw=10,target_mwh=40),
        dict(name='3箱：最小尾组回路反例',count=3,unit_mwh=5.015,target_mw=8,target_mwh=12),
        dict(name='8箱：95%检查与100%需求的差别',count=8,unit_mwh=5.015,target_mw=10.4,target_mwh=35),
    ]
    sections = []
    for case in cases:
        case['candidates'] = enumerate_case(**{k:v for k,v in case.items() if k!='name'})
        rows = []
        for c in case['candidates']:
            vals = [c['ratio'],c['blocks'],' / '.join(map(str,c['dc_distribution'])),
                    f"{c['pcs_per_block']} × {c['pcs_kw']}",
                    f"{c['station_nameplate_mw']:.3f}", f"{c['delta_mw']:+.3f}",
                    c['status'], '；'.join(c['legacy_errors']+c['legacy_warnings']) or '无']
            rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in vals)+'</tr>')
        shortlist = []
        for ratio in ('1:2', '1:4', '1:8'):
            pool = [c for c in case['candidates'] if c['ratio']==ratio and c['feeder_capacity']
                    and not c['legacy_errors'] and c['delta_mw'] >= 0]
            if pool:
                c = min(pool,key=lambda c:(c['delta_mw'],c['pcs_per_block']))
                shortlist.append(f"<li>{ratio}：{c['blocks']}个AC块，每块{c['pcs_per_block']}×{c['pcs_kw']}kW；"
                                 f"全站装机{c['station_nameplate_mw']:.3f}MW。设备及POI能力待确认。</li>")
        sections.append(f"<h2>{html.escape(case['name'])}</h2><p>DC铭牌 {case['count']*case['unit_mwh']:.3f} MWh；"
                        f"POI需求 {case['target_mw']:.3f} MW / {case['target_mwh']:.3f} MWh。</p>"
                        '<p>分比例选装机差额最小的算术对照项；不是工程最优排序。</p><ul>'+''.join(shortlist)+
                        '</ul><details><summary>展开全部组合及排除原因</summary><table><thead><tr>'+''.join('<th>'+v+'</th>' for v in
                        ['AC:DC','AC块数','每块箱数','每块PCS × kW','装机MW','较需求MW','评审状态','原检查信息'])+
                        '</tr></thead><tbody>'+''.join(rows)+'</tbody></table></details>')
    output = Path('output/ac_automation_review_20261017')
    output.mkdir(parents=True, exist_ok=True)
    (output/'candidates.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'review.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>集装箱AC自动候选 · 离线设计复核</title><style>
body{font:15px 'Segoe UI','Microsoft YaHei',sans-serif;color:#183043;background:#f4f7fa;margin:32px}
main{max-width:1400px;margin:auto}h1{color:#075c4e}h2{margin-top:40px}p{line-height:1.8}
table{border-collapse:collapse;background:white;width:100%;font-size:13px}th{background:#075c4e;color:white}
td,th{padding:10px;border:1px solid #d9e3e8;text-align:left}tr:nth-child(even){background:#edf4f7}
.note{background:#fff4d9;padding:18px;border-left:5px solid #e4ab29}</style><main>
<h1>集装箱 AC 自动候选：离线设计复核</h1>
<p><a href="catalogue-review.html">下一步：查看真实产品目录匹配与证据缺项</a></p>
<p class="note">全部为合成案例，5.015MWh仅是本轮示例输入，并非读取生产目录。每箱两路独立输出是显式测试假设。
无设备认证、POI净输出或保证能量结论；未连接数据库、未保存AC运行、未改变冻结逻辑。</p>
<p>逐比例展开全部现有PCS简化组合，不预先隐藏失败项，供核查筛选是否正确。
功率差额基于装机值；原能量警告比较DC铭牌和POI需求，不能视为保证能量验收。
本页尚不提供“最优”推荐，避免将缺失的工程数据包装成已验证方案。</p>'''+''.join(sections)+'</main></html>',encoding='utf-8')
    print(json.dumps({'checks':'passed','cases':len(cases),'candidates':sum(len(c['candidates']) for c in cases),
                      'html':str(output/'review.html')},ensure_ascii=False))


if __name__ == '__main__':
    main()

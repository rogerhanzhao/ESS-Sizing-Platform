"""Read-only historical catalogue reconciliation, never product approval."""
from pathlib import Path
import hashlib
import html
import json
import sqlite3


def main():
    source = Path('docs/ops-local/daily-logs/2026-10-16/db-snapshot.sqlite').resolve()
    out = Path('output/ac_automation_review_20261017')
    out.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        dc = dict(conn.execute("SELECT block_code,product_model,gross_energy_mwh,voltage_min_v,voltage_max_v,nominal_power_kw,max_current_a,source_ref FROM product_dc_block WHERE block_code=?", ('CALB-5P01596MWH-20FT-314AH',)).fetchone())
        records = [dict(r) for r in conn.execute('SELECT block_code,pcs_count,pcs_power_kw,transformer_kva,aux_load_kw,is_active,is_published,metadata_json,version_tag,source_ref FROM product_ac_block ORDER BY block_code')]
    cases = json.loads((out/'candidates.json').read_text(encoding='utf-8'))
    for rec in records:
        meta = json.loads(rec.pop('metadata_json') or '{}')
        rec['metadata'] = meta
        rec['quantity_matches'] = sum(
            1 for c in cases[0]['candidates'] if c['pcs_per_block']==rec['pcs_count']
            and c['pcs_kw']==rec['pcs_power_kw'] and c['feeder_capacity'])
        rec['binding_status'] = '仅数量相符，待确认' if rec['quantity_matches'] else '现有简化候选未覆盖'
        rec['officially_verified_compatible'] = False
    # Explicit evidence records, separate from catalogue raw fields. No kVA->kW
    # conversion and no product database updates are performed here.
    reviewed_capabilities = {
        'NR-PCS9567MV-10000-V2.3': {
            'source_url':'https://www.nrec.com/en/web/upload/2025/08/15/17552462399524524dn.pdf',
            'source_pages':[2,3], 'pcs_cabinets':4,
            'rated_apparent_kva_per_pcs':2500,
            'rated_active_kw_per_pcs':None,
            'dc_input_voltage_v':[1050,1500],
            'dc_current_a_per_pcs_source_expression':'1310*2',
            'independent_dc_domain_mapping':None,
            'auxiliary_peak_kva':21, 'auxiliary_operating_kw':None,
            'project_poi_capability_verified':False,
            'conflicts':['pcs_power_kw has apparent-power source',
                         'aux_load_kw has peak apparent-power source'],
        },
        'SINENG-EH-10000-HB-UD-10-33': {
            'source_url':'https://en.si-neng.com/Public/Uploads/uploadfile/files/20250625/EH10000HBUD1033.pdf',
            'source_pages':[1], 'dc_input_count':8,
            'independent_pcs_count':None,
            'rated_apparent_kva_by_temperature_c':{'30':11000,'45':10000,'50':8750},
            'rated_active_kw':None,
            'dc_input_voltage_v':[1000,1500],
            'dc_current_a_source_expression':'1403*8',
            'project_poi_capability_verified':False,
            'conflicts':['dc input count does not alone establish independent PCS count',
                         'ac_power_mw omits source apparent-power and temperature conditions'],
        },
    }
    assert all(p['project_poi_capability_verified'] is False for p in reviewed_capabilities.values())
    report = dict(source_snapshot=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  source_date='2026-10-16',live_verified=False,dc_product=dc,ac_products=records,
                  reviewed_capabilities=reviewed_capabilities,
                  formal_published_active_count=sum(bool(r['is_active'] and r['is_published']) for r in records))
    assert report['formal_published_active_count']==0  # audited snapshot, not live state
    assert all(not r['officially_verified_compatible'] for r in records)
    (out/'catalogue-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for r in records:
        m=r['metadata']
        cells=[r['block_code'],f"{r['pcs_count']} × {r['pcs_power_kw']:g}",
               str(m.get('container_type','待确认')),str(m.get('transformer_vector_group') or '待确认'),
               '启用/未发布' if r['is_active'] and not r['is_published'] else '其他状态',r['binding_status']]
        rows.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in cells)+'</tr>')
    (out/'catalogue-review.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>AC自动选型 · 目录证据复核</title><style>body{font:15px 'Microsoft YaHei',sans-serif;background:#f3f7fa;color:#183043;margin:32px}
main{max-width:1250px;margin:auto}h1,h2{color:#075c4e}p,li{line-height:1.9}table{border-collapse:collapse;width:100%;background:white}
td,th{border:1px solid #d5e0e7;padding:10px;text-align:left;font-size:13px}th{background:#075c4e;color:white}
.note{background:#fff2d4;padding:18px;border-left:5px solid #dba728}</style><main>
<h1>从算术组合到产品候选：目录证据复核</h1>
<p class="note">来源为2026-10-16生产数据库只读副本，不是今天的实时状态。18条AC记录均未发布。
按本轮拟议的发布及证据标准，正式候选为0；这是新设计的评审结论，现有产品匹配函数尚不检查发布状态。
“数量相符”不等于电气兼容。未修改目录、发布标志或生产系统。</p>
<h2>5MWh级集装箱的数据基础</h2>
<p>目录型号C173F5016，铭牌5.01596MWh，电压1164.8—1476.8V。已与本地原产品PPT第4页文字核对；
原容量字符串存在“5.015.96MWh”笔误，目录有归一化记录。PCS匹配必须使用实际运行快照，不能将示例5.015冒充精确产品值。
持续功率、最大电流及独立输出回路证据仍待补齐，0.5P文本不能单独代替电流/端口验证。</p>
<h2>本轮官方资料核查</h2><ul>
<li>NR 10MVA产品：PCS数量4，每PCS额定输出1250×2 kVA；辅电21 kVA为峰值。
目录2500kW/PCS及21kW辅电不能直接作为保证有功及运行辅电。</li>
<li>NR电压输入1050—1500V包含该DC目录电压范围，仅代表静态范围初筛；仍需逐输入电流、输出映射及满功率能力核对。</li>
<li>Sineng 10MVA产品：输出额定随温度变化；50℃为8750kVA。不能统一按10MW计算，亦不能把8个DC输入直接当作8台独立可控PCS。</li>
<li>变压器绕组额定分配、P-Q能力、损耗和辅电边界未齐全，不给POI净输出合格结论。</li></ul>
<p>官方来源：<a href="https://www.nrec.com/en/web/upload/2025/08/15/17552462399524524dn.pdf">NR V2.3数据表</a>；
<a href="https://en.si-neng.com/Public/Uploads/uploadfile/files/20250625/EH10000HBUD1033.pdf">Sineng数据表</a>。</p>
<h2>18条目录记录与第一组算术案例的数量匹配</h2>
<p>下列PCS数量和功率列为数据库原值，保留用于暴露单位/层级问题，不表示已被验证。未覆盖的string PCS等架构另行建模，不硬塞到现有输出回路合同。</p>
<table><tr><th>产品代码</th><th>目录PCS数量 × 原kW字段</th><th>实物外形记录</th><th>向量组记录</th><th>快照发布状态</th><th>初筛</th></tr>'''+''.join(rows)+'''</table>
<h2>实施前必须落实的数据合同</h2><ol>
<li>分开存储PCS机柜数、内部变流单元数、独立DC输入及可控/隔离域。</li>
<li>分开kW/kVA、额定/峰值、充电/放电、温度/海拔条件，禁止无条件互换。</li>
<li>每项关键能力保存来源、版本、适用条件和确认状态；补证据后才按现有治理流程发布产品。</li>
<li>简化候选外形只作概念；绑定真实产品后采用实物尺寸及拓扑，冲突必须可见。</li>
<li>先离线比较NR 5MVA、NR 10MVA和Sineng 10MVA三种架构；有条件的目录匹配不得升级为正式推荐。</li></ol>
<p><a href="review.html">返回算术候选对照</a></p></main></html>''',encoding='utf-8')
    print(json.dumps({'ac_records':len(records),'published_active':report['formal_published_active_count'],
                      'review':str(out/'catalogue-review.html')},ensure_ascii=False))


if __name__=='__main__':
    main()

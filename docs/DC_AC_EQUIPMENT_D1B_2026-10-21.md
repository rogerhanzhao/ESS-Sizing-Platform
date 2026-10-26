# D1b：设备能力修订与逐组放电参考检查（本地）

主线保持314Ah / 416S / 20ft的12簇主箱加一个10/8簇尾箱。本阶段在D1a显式连接上补设备能力资料与数值检查，不接正式采用，不改变原5MWh的DC/AC计算、旧产品匹配或图纸生成。

## 1. 本轮职责

| 模块 | 新增职责 |
|---|---|
| `schemas/ac_equipment_capability.py` | 严格PCS/变压器能力包及独立设备工况；未知值保留None，不推额定值 |
| `infra/db/models/ac_equipment_capability.py`、迁移0013 | 独立能力修订和审核事件，不回填或激活旧产品 |
| `services/ac_equipment_capability_service.py` | 管理员登记、审核、退役、精确版本引用、完整性及当前性检查 |
| `services/dc_ac_equipment_assessment_service.py` | 消费D1a连接和原case损耗链，检查逐端口/PCS/绕组/整台变压器 |
| `ui/dc_ac_equipment_review_view.py` | 英文静态诊断表，区分功率边界、已知失败、缺项与发布状态 |
| `scripts/rehearse_dc_ac_equipment.py` | 独立SYNTHETIC库与可重复场景；不写源库或生产 |

D1a复验148项通过后实施D1b。所有机制数据均是SYNTHETIC，不是CALB、PCS厂家或变压器厂家的真实额定资料。

## 2. 数据库维护及审核

能力包不是`ProductACBlock.metadata_json`的随意扩展。独立组件表按`kind + package_code + revision`唯一保存规范化payload及SHA；引用指明资料包代码、修订、SHA和证据位置。实际型号、厂家、技术文件来源与温度/频率条件必须显式记录。

生命周期：`draft → parameter_review → candidate_only → retired`。资料纠错新建修订，不原位改写已审核参数；退役不可恢复。Active/Published是本注册库状态派生值，不能单独开启以跳过审核，也不会修改原AC产品的两个标志。Candidate-only只表示所录资料经过本地行政审核，并不表示参数完整、厂家适用批准或可正式选型。

公开服务`EquipmentCapabilityRevisionService`要求管理员：

1. `create(package, evidence_ref)`登记不可变版本；
2. `inspect(id)`和`list_revisions(kind)`查看参数、缺项、事件和当前审核状态；
3. `transition(id, expected_status, target_status, evidence_ref)`按当前状态审核/退役；
4. `resolve_reference(reference, kind)`按完整身份解析，未知或SHA不符拒绝。

每项事件带顺序、前序hash并绑定payload SHA，检查完整状态链。SQLite审核先申请写锁并做乐观状态核对。评估前后复查review token，在复核点发现退役/变化则整份评估作废；DC来源最终复核后再复查设备，以捕捉该阶段撤回。各检查点是分别读取，不构成跨来源原子快照，正式采用须在D3原子重验。包内自称已批准、任意metadata、目录可见性或内容hash均不能替代当前注册库审核。

当前提供本地登记/审核服务与隔离浏览器验证页；尚未把新能力维护或自动推荐加入原生产页面流程。

## 3. 能力字段

PCS分别保存整机DC电压窗、持续总电流及其厂家定义、持续DC放电kW、AC kW/kVA、AC电压，每输入端口另列电压/持续电流/功率和所属物理DC bus group。

分配中的实际bus与能力包bus group必须双向一致，不能把共母线口画成独立口，或把独立输入并在一起。能力包可以有未用物理端口；D1a分配表只列实际使用口，不强迫全部使用。

同bus接多个DC域，须同时有最大域数、准确产品修订SHA、显式输出分区SHA及并联证据。少一项保持pending，明确不适用则失败。相同Ah或简单allow_parallel不能授权。分区hash不含实例编号/箱数，保留真实域参数与来源。

变压器分别保存总kVA、HV电压、向量组、每个LV绕组的独立电压与持续kVA。已知PCS同工况kW不得大于kVA；端口总额定值不要求等于整机值，各绕组容量也不强制等于或平均分配总容量。

## 4. 功率、电流和工况边界

原Stage1的Pdc位于DC cable之前，因此本阶段只消费其既有定义：

```text
DC产品输出参考Pdc
  × 原case eff_dc_cables → PCS输入参考kW
  × 原case eff_pcs       → PCS交流端参考kW
  ÷ 显式项目|PF|         → PCS交流端单点参考kVA
  → 按显式连接归集到每个LV绕组及整台变压器
```

下游再乘原case的MVT/AC cable/HVT效率，核对是否回到原Stage1的POI功率。这只是原损耗链的算术一致性，不证明实际PCS效率曲线或POI保证。未改变效率值、选型阈值、PCS数量或保证年能量。

电压窗检查方向为`PCS min ≤ DC产品min`且`PCS max ≥ DC产品max`，每端口和整机分别检查。实际端电压还受电缆压降影响，所以铭牌窗筛查通过仍有逐口terminal-voltage待核项。

源端参考电流保持`Pdc / DC产品Vmin`，不先乘电缆效率后再除源端电压。只有明确声明“中间只有被动DC电缆、没有DC/DC或分流”时用于端口持续电流筛查；跨独立口相加核对总电流，还须厂家明确限值为各口电流之和。未知路径或定义不推测通过。

设备环境温度与电芯衰减曲线温度分开；本包额定参数只用于声明的设备温度区间，不外推降额。频率来自被绑定的项目工况。PF、MV bus电压和证据单独输入，未知PF不默认1，MV bus不自动等同POI电压。已用PCS AC电压与接入的LV绕组电压须一致。

独立复核补正：温度范围即使缺一端，超过另一已知端仍必须失败，同时保留缺项；未知PF下实际kVA继续为None，但`S ≥ |P|`给出了确定下界。若已知有功参考1090.91kW而额定仅500kVA，任何有效PF都不可能满足，应单列下界失败，不能降为pending。这不等于将PF假设为1；额定高于下界时仍不能推断通过。

## 5. 输出和已验证的局部失效

结果含逐项pass/fail/pending、每端口与PCS的参考功率/电流、逐绕组及总变压器kVA、当前能力修订、源manifest/比较/分配签名。数值显示两位小数，数据库UUID和hash不出现在页面正文。

| SYNTHETIC场景 | 检查结果 |
|---|---|
| DC cable99%、PCS98%、POI2MW | DC产品2061.43kW→PCS输入2040.82kW→PCS AC2000.00kW，边界明确 |
| PCS需要1148.33kVA、额定1120kVA，但kW足够 | 仍因kVA不足失败 |
| 总变压器5000kVA，但LV1需1148.33、仅额定900kVA | 仅该绕组超限，不以全站/总容量掩盖 |
| 端口电流足够，整机参考936.56A、总限500A | 整机电流失败 |
| PCS窗口下限1200V，产品下限1164.8V | 窗口不包含产品范围，失败 |
| 能力修订退役 | 不再使用其额定值，相关检查pending |
| 项目PF未知 | 所有相关kVA保留未知，不按1计算 |

整体始终`comparison_only=true`、`downstream_ready=false`。缺失充电、完整P/Q包络、真实端电压、保护控制、tap及详细并网设计等仍待核，不从单点放电筛查扩展为全工况通过。

## 6. 本地验证与后续

七个新演练库integrity为ok且无FK异常。另从原库只读备份副本演练0010→0013，逐表内容hash确认既有记录保持一致；原库仍0010，继承的16条FK异常没有增加。新增迁移还单独验证upgrade/downgrade及旧表保留。

最终自动/浏览器记录保存在`output/flexible_dc_phase_d1b_20261021/validation-result.json`；本地合成验证页为8526。没有源库迁移、实际产品激活、正式运行写入、GitHub推送或生产部署。

最终自动验证：全量1844项通过（550.44秒）；本轮新增230项。另行focused设备匹配42项、schema/registry/migration/UI containment187项、页面7项均通过。编译和冻结模块/原制图差异检查通过。审查期间发现并修正了typed工况对象被修改后可绕过PF校验的问题，以及最低电压表格的需求/额定方向问题，均有回归覆盖。

浏览器逐一验证上述七类场景及下载后预览保留；最后将PCS表格从八列收窄至六列，改善设备编号换行，另7项UI/containment复验通过（11.29秒）。原库在全量测试后再做逐表hash核对，仍与迁移演练前完全一致。

用户再次复验记录：先对原版本重跑全量1844项（512.82秒），另做独立边界审查，发现并修正上述两处缺参掩盖已知失败，以及最终DC复核时设备撤回的漏查检查点。新增12项回归；增加部分温度范围和未知PF必然不足两个SYNTHETIC浏览器场景。修正后的最终验收另见`output/flexible_dc_phase_d1b_recheck_20261021/validation-result.json`，旧验收日志保留作历史。

修正后全量1856项通过（504.63秒）；新增12项通过（20.94秒）、原42项设备检查通过（89.86秒）、7项页面检查通过（10.23秒）。九个新合成库均完整性ok且无FK异常；原七类场景的数值及状态逐项保持一致。原5MWh冻结模块和原制图模块未修改。

下一步D2才开始有界自动AC方案枚举；所有候选共同消费本阶段校验器，区分已知失败与证据不足。随后D3处理正式采用身份和旧图失效，再由E补专用异构SLD/Layout/报告。原5MWh路线继续保留。

## 7. 再次独立复验：项目元数据与POI边界

再次对原1856项全量复验通过（605.21秒），并将九个既有合成场景重新计算，完整输出逐项一致。额外探针发现独立pilot创建`SizingCaseInput`时漏传POI位置、电压及频率，可能错误回到AC侧、33kV、50Hz；D1b也没有拒绝本来合法的DC侧POI比较源。即使五段效率均100%且算术闭合，也不能将DC参考点解释为AC侧POI。

修复仅在管理员pilot输入适配和D1b诊断适配层：

- pilot传递`poi_is_dc_side`、实际`poi_nominal_voltage_kv`、`poi_frequency_hz`及原选择`poi_frequency_option`。频率TBD只阻止pilot并清除其临时预览；不调用`st.stop`、不返回页面、不影响原Run Sizing计算/保存/导出。
- D1b先完成源hash、来源及分配复核，再要求源显式`poi_is_dc_side is False`；DC侧或未知位置受控拒绝，不生成误导的AC/POI参考表。布尔以外的0/1或字符串不能替代明确False。
- 频率TBD不使用模型默认50Hz；若提供数值选项，须有限且与保存的Hz一致。`None option + 明确数值Hz`保留programmatic接口兼容，仅证明该源声明的数值，不证明人工确认或设备适用性。
- POI电压随源保留；设备内部MV bus仍需单独声明，不把二者自动等同。

旧pilot早期已经丢失的元数据无法可靠恢复。相关比较必须通过修复后的前台，按实际AC/DC边界、电压及频率重新计算；不从全100%效率猜测，不改写旧下载文件，不重标或静默重算旧hash。本轮不迁移或采用任何历史结果。

新增15项D1b来源边界回归和6项真实DC页面AppTest；另由独立代理对来源篡改、撤回及频率冲突作只读复核。12个合成演练场景完整性均为ok、无FK异常：原九类不变，DC侧POI和TBD被明确拒绝，60Hz项目对三台50Hz设备逐一失败。实际源库与保留副本的32个既有数据表记录逐项一致，仍处0010，16条原有FK问题未增加。新增验证结果保存在`output/flexible_dc_phase_d1b_finalcheck_20261021/`；正式全量及浏览器结果以该目录最终`validation-result.json`为准。

最终修正后全量1877项通过（688.62秒）；新增21项独立定向通过（79.24秒）。两条Pydantic序列化警告来自故意构造布尔频率选项的非法数据测试，校验已拒绝该数据。浏览器验证DC侧POI、TBD拒绝和三个60/50Hz逐项不匹配；正常场景下载后预览仍在，实际下载JSON与重算结果完整一致。编译、空白检查及冻结模块/原图diff检查通过。D1b验收完成仍不等于全工况/正式采用完成；下一步可进入独立D2候选生成验证。

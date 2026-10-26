# D1实施前接口设计：混合箱体逐域AC分配

这是C2b后的下一步设计，不表示已完成AC sizing或厂家设备兼容批准。主线仍是12簇20ft主箱配一个8/10簇尾箱，原5MWh AC与SLD路线保持原路。

2026-10-21实施记录：D1a已在本地实现严格连接合同、当前DC来源复验、完整性/母线边界校验及上游DC参考功率归集；详见`DC_AC_ALLOCATION_D1A_2026-10-21.md`。设备能力数值校验和正式采用仍待D1b以后，不能把本阶段映射有效解释为AC sizing通过。

D1b本地实施见`DC_AC_EQUIPMENT_D1B_2026-10-21.md`：已加独立能力修订审核和单点放电数值检查；尚不认证全工况兼容、正式采用或图纸。自动方案枚举仍属于下一步D2。

## 1. 已核实的接口缺口

| 实际模块 | 已有内容 | 新路径不能由此推定 |
|---|---|---|
| ProductDCBlock | S/P、能量、总功率/电流、电压窗、外形 | 独立输出域数量、端口额定值及保护关系 |
| ProductACBlock | PCS型号/kW/数量、总变压器kVA、HV/LV电压、效率/aux | PCS直流电压窗、连续电流、端口拓扑、每LV绕组容量 |
| AC产品metadata | dc_inputs、transformer_topology/vector_group/cooling等 | metadata有值不等于能力合同完整或厂家确认 |
| ac_mixed_station | 每AC Block的pcs_count/pcs_kw/dc_blocks | 逐箱产品修订、unit_id、8/10/12簇输出域差异 |
| 现有电气拓扑与SLD | 既有1/2输出假设、标准同PCS组合、混合站head-fleet投影 | 任意输出数、全站逐箱异构连接或不等LV绕组容量 |

`ac_block_product_match.match_ac_block_products`按PCS数量及单机kW匹配，`engineering_data_status=complete`只检查向量组与拓扑存在，不能解释为DC兼容通过。该查询当前也没有按Active/Published过滤；D1须明确新能力包的生命周期/审核资格并补测试，不能把这个旧查询结果当作新产品激活许可。本轮没有改写旧目录语义或旧匹配结果。

## 2. 新合同的最小结构

建议独立的 `dc_ac_allocation_v1`，不塞入旧的平均箱数ratio：

```text
source:
  dc_manifest_sha256
  candidate_comparison_sha256
  case/duty basis

unit_assignments:
  physical unit_id -> ac_block_id

dc_connections:
  domain_id -> PCS instance -> PCS input port -> DC bus identity

lv_connections:
  PCS instance -> transformer instance -> LV winding -> LV busbar

equipment:
  PCS and transformer capability-package revision/hash/evidence

validation:
  source current / topology / voltage / continuous current
  box and port discharge limits / PCS AC duty
  transformer winding and total kVA / outstanding charge and P-Q duty
```

PCS能力包须明确输入端口是否电气独立、适用电压范围、端口/整机持续电流、充/放电功率、并联许可与条件。变压器能力包须明确总kVA、每个LV绕组的电压/kVA、向量组、PCS分配及已确认工况。缺项保持pending，不按总kVA平均分给两路LV，也不将Published或任意JSON存在等同审核通过。

## 3. 分配验证先于自动推荐

1. 每个域必须来自同一已签名C2b清单，不能丢失、重复分配或用平均容量替代。每个物理箱体保留原产品修订。
2. 一个独立DC域不能同时跨接多台PCS；不同PCS不得共享同一DC母线。多个域并到同一PCS输入前，须有明确并联适用证据，不能因为电芯Ah相同就许可。
3. 同箱独立输出必须落在同一个AC Block，沿用已有物理边界；输出路数不能由簇数或rack数推算。
4. 每台PCS接入一个明确LV绕组；逐PCS、逐端口和每个整箱都核对实际分摊需求，禁止全站总MW掩盖短尾组不足。
5. 电压窗、端口及整机持续电流、实际放电功率必须同时闭合。充电、无功/P-Q、温度降额等尚未提供时单列pending，不把放电检查扩展成全工况结论。
6. 原AC阈值、PCS标准库与保证年能量定义继续保留。新增验证器先解释显式映射；验证器稳定后，再由有界推荐器生成多个设备颗粒度候选，共同调用同一个验证器。

## 4. AC身份、图纸和历史数据

当前 `ac_run_service._IDENTITY_FIELDS`没有新composition/allocation签名。仅把新数据附加到output，会更新同一AC run快照但可能继续复用旧配置身份；`resolve_preferred_ac_snapshot`只核查对应DC run，也不能证明新合同当前有效。

接正式采用前须将 `allocation_contract_sha256`纳入新路径AC身份；无该字段的旧输出保持原hash。新allocation签名同时覆盖manifest、比较结果、设备能力包版本、逐域映射及审核依据，并进入SLD/Layout/Report输入签名。换箱型、换修订、改端口或改PCS后，旧图须判定失配。`adopt_saved_ac_run`现有清理SLD/Layout运行态的行为继续保留。

## 5. 本地实施与验收顺序

- D1a：schema与显式人工映射验证器；用同一个BOM验证完整/缺失/重复/跨AC Block/共母线冲突。
- D1b：独立版本化PCS/变压器能力资料包；逐项区分确认值、假设、缺项。只读核查旧Active/Published行为，新增资格不能绕过审核。
- D2：有界自动AC候选；候选逐组与全站闭合，保留设备粒度差异，不在缺成本时称最低价。
- D3：采用前身份和失效闸门；对旧12簇标准、历史run恢复、重算复用、混合头/尾组做回归。
- E：专用异构SLD、布局、报告适配共同消费分配合同，原5MWh引擎不替换。

本文件记录已梳理的实际字段缺口与下一步接口，不改数据库，不将当前机制测试数据转为真实能力资料。

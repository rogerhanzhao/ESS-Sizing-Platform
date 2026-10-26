# D2a：本地有界AC候选生成

**历史研究记录，非当前实现：** 用户要求回归原页面后，本模块的代码、独立UI、fixture及专属测试已从应用路径清理，并保存在工作目录外的可恢复归档。当前不使用本设计继续扩展；请以`FLEXIBLE_DC_EXISTING_UI_INTEGRATION_2026-10-21.md`为准。

本阶段承接D1b独立复验，主线继续是314Ah/416S/20ft的12簇主箱加一个10/8簇尾箱。新增机制只做局部比较，不改原5MWh sizing、手动混合AC、SLD、布局和直接下载技术方案流程。不接入生产路由，不将SYNTHETIC参数当作真实产品批准。

## 输入与产品资格

输入是调用方独立保留hash的C2b结果、显式项目放电工况，以及`AcCandidateSearch`。严格typed schema拒绝未知字段、重复ID/端口/输出标签/修订SHA和非法预算。组件继续通过D1b独立修订库的精确code/revision/hash/current-review解析，不使用旧ProductAC的Active/Published代替审核。

每个AC assembly模板声明组件修订、结构来源及所有PCS槽位；每槽位声明允许DC产品修订SHA、输出label→PCS端口、所接变压器LV绕组。本阶段每个完整DC箱体占一个PCS槽位，选中的模板必须满槽；不足一个大组时须使用明确的小模板，不能自动保留空PCS或按平均容量补齐。模板的evidence字段只声明搜索边界，不证明整个装配获准。

不支持跨箱共PCS、单箱输出拆给多PCS、跨输入并联或任意自动布线。一个箱有多个明确独立输出时，可以分别映射到同一PCS的不同独立母线输入。源manifest没有输出定义则拒绝；不由簇/rack数量猜测。已知同母线端口的模板在本阶段排除，即使其他阶段可能有并联许可，也不在此隐式启用。

## 有界枚举与校验

按产品修订多重集做exact cover，确定性绑定真实unit_id。完全等价的槽位规约掉同型排列，绕组或PCS不同的槽位保留差异。每一个完整候选都实例化为既有`DcAcAllocation`并调用同一个D1b校验器，没有另写“简化可行”公式。

逐端口、整台PCS、每个绕组和整台变压器，以及源保证年能量/DC功率与全站有损效率链共同核查。局部短尾组不足仍标记known_failure且不排名，不能被全站总额定功率掩盖；资料缺失保持pending，未知PF不默认1。任一方案始终`comparison_only=true`、`downstream_ready=false`。

默认计算预算：1000搜索节点、20个完整候选评估、最多返回10个详细候选。schema分别限制为100000/200/20，模板最多16个、槽位/声明输出最多16，单次计算最多256个物理箱。这些都是本地计算/内存预算，不是工程分组比或对冻结阈值的修订。搜索节点统计包括部分槽位与cover展开。达到节点或评估预算明确标记incomplete；返回详情数量限制不等于搜索截断，全部已评估的摘要仍留在JSON。不能据截断结果声明无解或全局最优。

已知失败排后；其余先显示总额定量已知的候选，再按总PCS kW、总变压器kVA及设备数量作明确的比较顺序。不同指标存在取舍，不称最低价、最优或工程可行。未知总额定量不填0、不参与该数值排名；即使有比较序号，所有工程证据仍待核。

批次结束后再次核查DC源和所有使用组件审核token；检查点发现撤回则整批作废。它们仍是分别读取的复核点，不是跨数据库原子发布快照。D3正式采用仍须原子重验与新身份/图纸失效闸门。

## 模块与页面

- `schemas/dc_ac_candidate_search.py`：声明模板、精确修订许可和计算预算。
- `services/dc_ac_candidate_search_service.py`：有界exact cover、实例化完整分配、逐候选复用D1b、批末复核与比较摘要。
- `services/dc_ac_equipment_assessment_service.py::validate_equipment_source_boundary`：D1b与D2共享同一AC POI/频率前提校验；判断语义未变。
- `ui/dc_ac_candidate_review_view.py`：独立英文静态表格、明确搜索截断、逐组/PCS/绕组诊断和单个完整JSON下载。
- `scripts/rehearse_dc_ac_candidates.py`：只在新建output隔离目录生成明确SYNTHETIC演练库。

新页面不接原main app，不写现有DC/AC run，也不生成/采用SLD、Layout或技术方案。页面保持两位小数，不展示数据库UUID/hash；JSON保留重现所需请求、工况、来源身份、组件复核点及完整分配。

## 验证与后续

测试/浏览器结果记录在`output/flexible_dc_phase_d2a_20261021/validation-result.json`。独立枚举oracle覆盖多个修订族、多模板、第二槽位锚点和等价槽位；真实合成库覆盖12+10、12+8、逐绕组/局部功率不足、独立双输出、缺PF、来源能量不足、预算截断和撤回。

8簇正例明确重算为2MW/6.5MWh目标；同样12+8在原2MW/7.2MWh目标下能量不足的负例必须失败。没有为通过测试修改保证年算法或放宽判据。

下一步应先补真实组件及assembly适用证据并复验，再扩展单箱拆接多PCS等明确新拓扑。D3身份/采用和E专用异构图纸/报告仍未开启；原5MWh流程继续原路。

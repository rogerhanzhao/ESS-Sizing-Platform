# 阶段 C1：单一 container 规格的隔离比较试算

状态：本地试验接口及管理员面板；默认关闭。未开放采用方案、批量最优组合、混合尾箱或生产发布。

## 接入与不变项

新 `services/dc_product_comparison_service.py` 只做数据适用检查和输入适配，计算仍调用原 `size_with_guarantee`。新 `ui/dc_product_comparison_view.py` 只显示其结果。

DC页主表单后新增受控入口：仅进程 `CALB_DC_PRODUCT_COMPARISON=1` 且管理员可见。关闭时不查询修订表、不加载比较面板，原数据源选择、场景开关、Run Sizing、保存、历史恢复和后续AC/图纸/报告链继续原路径。未修改冻结七个模块或 `calb_diagrams`。

比较面板使用已加载/最近提交的DC表单输入，并再次显示POI P/E、评估年、寿命及频次；未提交的表单编辑不会纳入。每次明确选择一款当前有效candidate_only修订，不能选柜式或混合配置。不同产品试算各自绑定精确电芯及修订，不能跨电芯共用曲线包。

## 曲线包与审批记录

一个目录curve_code并不能证明运行时SOH/RTE适用。C1另外要求由可信管理员提供的比较用曲线包，及从独立审核登记取得的摘要。JSON schema_version=1包含：

| 内容 | 要求 |
|---|---|
| 包身份 | package_code、version、review_status=comparison_approved、reviewed_by、approval_ref |
| 精确绑定 | product_revision_sha256、product_cell_id，必须与当前有效修订一致 |
| 性能边界 | measurement_boundary=DC；SOH按BOL相对保持率，0年100%，S&C另由原管线处理；RTE SoH分档对应相同的相对SoH定义 |
| 工况条件 | DOD范围、曲线参考温度范围、待机SOC范围、寿命上限、RTE修正百分点、单调处理开关 |
| SOH profile适用记录 | Profile_Id、倍率范围、循环频率范围、evidence_ref |
| RTE profile适用记录 | Profile_Id、倍率范围、循环频率范围、evidence_ref；不能因SOH已检查就省略RTE频次依据 |
| 四张运行表 | soh_profile、soh_curve、rte_profile、rte_curve，保留原列名；RTE额外要求显式Soh_Band_Max_Pct |

界面最多读取2MiB UTF-8 JSON，拒绝重复键、NaN、坏编码及非对象。温度、待机SOC必须填写，不默认25℃或50%。

登记摘要是 `package_sha256(json.loads(...))` 的规范JSON摘要，不是PDF摘要或JSON文件原始字节摘要；缩进与键顺序不影响它，记录数组顺序仍属于内容。输入包不会被自动计算摘要并填入登记框，以免把完整性检查冒充审批。

摘要不构成签名，也不证明审批记录真实。此接口没有新建公司级审批/撤销登记服务；当前仅限可信管理员的本地比较。后续正式采用前仍需持久化来源、适用关系、权限及撤销策略。

## 迭代预检查

用户指定评估预算max_iter=1..60，默认10。它是本次试算允许的完整预算，不会自动缩小到“能通过”的数值。

先调用原Stage2构造初始箱数N，再用原rebuild依次得到N到N+max_iter−1及其舍入后的总容量。对每个可能箱数：

1. 使用原SOH/RTE最近profile选择函数，不提前过滤后换成另一曲线；并列最近且无法唯一解释时阻断。
2. 验证实际选中profile的倍率与循环频率适用证据。
3. SOH的0至项目寿命每年必须有唯一有效行；拒绝缺年、重复、NaN、非整数年份或越界值，避免核心末年沿用。
4. 用未舍入SOH检查原核心会实际选中的RTE Min档，确认其Max覆盖，拒绝fallback和档位缺口。先按归一化Min排序检查RTE单调性，防止百分比/小数混用让核心cummin静默改值。
5. 检查归一化后的实际效率/DOD/基础与有效RTE等在合法范围，也检查来自baseline.defaults的值，防止可选输入为None时绕过表单检查。

全部通过后才调用一次原 `size_with_guarantee`。必须在请求预算内收敛，最终数量、profile、倍率与预检查一致，总DC连续功率足够，修订在计算结束时仍有效。

此预检查故意保守：即使核心可能较早收敛，后续预算内未覆盖的倍率也会导致拒绝。可以提交有适用依据的较小预算，但仍须收敛；接口不自动减预算绕过检查。

## 结果范围

返回原 `DcPipelineRunSnapshot`、产品修订/曲线包/工况溯源与预检查轨迹，标记comparison_only=True、downstream_ready=False。面板只显示返回的设备表及年度结果，不重新计算，不写入现有选中run或AC状态。

总名牌功率足够不能证明PCS端口电压、电流、短组功率、变压器绕组或现场安装可行。本阶段没有自动保存/采用按钮，不能把比较结果直接当AC/SLD/Layout/技术方案的已批准输入。

## 验证

独立测试采用全部显式标注的synthetic产品、曲线和独立SQLite，不作为CALB实际产品性能数据。

验证包含：与原管线同bundle结果完全一致；base bundle、输入包及DB内容不变；全60轮预算；后续潜在数量越界在核心调用前拒绝；profile不换档/并列阻断；真实多轮增配profile切换；5.0004MWh舍入路径；RTE原始SOH及混合单位；默认参数继承；过期修订/缺曲线/工况不符/未收敛拦截；管理员与缺schema/无候选页面，以及错误不影响当前run。

最终全量 **1142 passed / 308.02秒**，编译及git diff空白检查通过。C1服务/页面加冻结闸门联合定向95项通过。日志：`output/flexible_dc_phase_c1_20261020/full-regression.txt`。Streamlit AppTest属于页面模拟，尚不等同于真实浏览器验收。

额外隔离演练构造三个明确标为SYNTHETIC的8/10/12串规格，分别调用同一接口，返回各自指定产品及不同箱数/保证年能量；全部comparison_only且downstream_ready=False。演练数据与结果在`output/flexible_dc_phase_c1_20261020/synthetic-only/`，不是CALB产品参数，未写真实产品库或当前方案。

## 实际产品资料

6.262MWh规格书已确认588Ah、8条1P416S、4 rack，但功率0.5P/0.25P等存在冲突。10.051MWh规格书已确认661Ah、12条1P396S及1/3/12路输出，但尺寸/重量/版本有冲突。两份都未提供可直接用的完整SOH/RTE时序及全部电气适用依据，因此本轮没有伪造曲线包、激活或修改真实产品。

314Ah既有资料的只读核查明确读到12串5MWh及双串rack结构，但尚未核实发布的8/10串container规格和精确电芯修订绑定。现有平台导入曲线仍可存在，缺口是对具体型号/修订/工况的受控适用关系，不能笼统说系统没有曲线。项目专用8/10串工程变体还须有BOM、保护配置及项目适用限制，不自动成为全局默认。证据记录：`output/flexible_dc_phase_c1_20261020/314Ah-product-evidence-review.md`及DC Block/NextGen-Products资料目录。

后续先核实真实产品参数与性能数据；再逐款做本地C1比较、保存/恢复溯源契约及下游规格验收；通过后才进入C2混合主箱/尾箱/尾柜和D阶段逐组AC匹配。

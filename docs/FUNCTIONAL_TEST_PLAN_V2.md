# Functional Test Plan V2 — 业务级全功能 Web 测试大纲

Date: 2026-07-14
Status: **DRAFT — 待讨论确认后执行**
Supersedes: `FUNCTIONAL_TEST_PLAN_V1.md`（V1 为已执行的验收记录，保留作为回归基线与缺陷史）

---

## 0. 与 V1 的关系

- V1 覆盖了主业务流（Project → Case → Run → DC → AC → SLD → Arrangement → Report）的
  happy-path 验收，并修复了 FT-20260714-01 ~ 06 六个缺陷。
- V2 目标：**逐页面、逐控件**（按钮、数字输入、下拉、勾选、上传、下载）的业务级测试，
  加边界值/非法值/状态机测试，加平台级测试（权限、导航、会话、持久化），
  并为未完成模块（Concept Master Layout、SLD official 模式等）预留测试章节。
- V1 中已修复缺陷对应的场景全部纳入 V2 回归用例（标注 `[V1-回归]`）。

## 1. 测试环境

| 项 | 值 |
| --- | --- |
| 仓库 | `D:\CALB_SizingTool`，分支 `ops/ubuntu-docker-coexist-20260311` |
| 测试实例 | 本地隔离实例 `http://127.0.0.1:8599`（不碰 8511 主库、不碰服务器库） |
| 数据库 | `var/_uitest_copy.sqlite`（从主库复制，测试前重新快照） |
| 环境变量 | `CALB_DATABASE_URL=sqlite:///D:/CALB_SizingTool/var/_uitest_copy.sqlite`、`CALB_OPLOG_ENABLED=false` |
| 测试账号 | `uitest_admin`（admin 角色）；另需 guest 入口验证 |
| 已知良好回归 Run | project `test` / case `test-case` / run `4ffb9a93-7f05-49f3-a153-3846e322acc3`（400 MW / 800 MWh） |
| 前置命令 | `python -m alembic upgrade head`；`python -m pytest tests/ -x -q` 全绿后再开浏览器测试 |

## 2. 用例编号、优先级与缺陷分级

- 用例编号：`<模块前缀>-<两位序号>`，模块前缀见各章。
- 优先级：**P0** 主业务流阻断即测；**P1** 核心控件与数据正确性；**P2** 边界/异常输入；**P3** 文案、提示、体验。
- 缺陷分级：**S1** 崩溃/数据丢失/错误结果入库；**S2** 主流程阻断；**S3** 功能错误但有绕行；**S4** 文案/样式。
- 缺陷记录格式沿用 V1：`FT-<日期>-<序号>`，含 Symptom / Root cause / Fix，写入本文档第 12 章。
- 执行约定（待讨论）：S1/S2 即时修复并回归；S3/S4 先记录、批量处理。

## 3. TG-A 认证与账户（AUTH）

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| AUTH-01 | P0 | Admin 正常登录（用户名+密码） | 进入 Workbench，侧边栏显示完整导航 |
| AUTH-02 | P1 | 错误密码 / 不存在用户登录 | 明确错误提示，不崩溃，不泄漏用户是否存在 |
| AUTH-03 | P2 | 用户名/密码留空提交 | 表单校验提示，不产生 traceback |
| AUTH-04 | P1 | 首次建库时 Create Admin Account 表单（用户名、显示名、密码、确认密码、token） | 密码不一致/缺 token 被拒；成功后可登录（在全新空库实例上验证一次） |
| AUTH-05 | P1 | Guest 模式进入 | 导航仅含 guest 允许页面（默认落在 DC Sizing）；Workbench 等受限页不可达 |
| AUTH-06 | P1 | Guest 会话残留 `main_nav="Workbench"` 时刷新 | 导航被钳制回允许页（app.py nav clamp 逻辑） |
| AUTH-07 | P1 | Guest 打开 Report Export | 显示 “Sign In to Enable Export” 按钮，点击跳转登录 |
| AUTH-08 | P2 | 登出后回退/刷新 | 不能继续访问受限页面 |

## 4. TG-B 工作台 Workbench（WB）

对应 `workbench_view.py`，含三态引导（`WORKBENCH_UI_HANDOFF_2026-07-12.md`）。

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| WB-01 | P1 | 空工作区（无项目）状态 | 只显示三步进度指示 + “Create your first project” 卡片；无空的 Case/Latest Run/Run Registry 面板 |
| WB-02 | P0 | New Project：输入 Project Name → Create Project | 创建成功、自动设为 active、rerun 后进入“有项目无案例”态 |
| WB-03 | P2 | Project Name 留空 / 重名 / 超长 / 特殊字符（中文、`/`、引号） | 有校验或安全落库，不产生 traceback |
| WB-04 | P0 | New Case：Case Name + scenario 下拉 → Create Case | 创建成功、成为 active case；出现 “Open DC Sizing” 引导 |
| WB-05 | P2 | Case Name 边界同 WB-03 | 同上 |
| WB-06 | P1 | 项目下拉切换 + “Use” 按钮切换项目 | active 项目变化；DC 表单陈旧控件状态被清除 `[V1-回归 FT-05]` |
| WB-07 | P1 | 案例 “Use” 切换 | 同上；active case 正确 |
| WB-08 | P0 | Latest Run 面板 restore（下拉选 run + 恢复按钮） | 路由到 DC Sizing 且 POI/寿命/效率/场景/高级输入全部恢复 `[V1-回归 FT-05]` |
| WB-09 | P1 | 快捷按钮 DC/AC/SLD/Report 的禁用逻辑 | 无 case 时 DC 禁用；无 run 时 AC/SLD/Report 禁用；有 run 后全部可用 |
| WB-10 | P1 | Run Registry 列表展示 | run 列表与 DB 一致，无 Arrow 序列化报错 |
| WB-11 | P2 | 同名项目下多案例、多 run 的显示排序 | 最新在前、标签可区分 |

## 5. TG-C 目录页（DIR）

Project Directory / Case Directory（`projects_view.py`、`cases_view.py`）。

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| DIR-01 | P1 | Project Directory：下拉选择 + Open Project | active 项目切换并路由 |
| DIR-02 | P2 | 无项目时的空态 | 显示 “Go to Workbench to create one” 按钮且可跳转 |
| DIR-03 | P1 | Case Directory：下拉 + Open Case（active case 时按钮禁用） | 切换正确、禁用态正确 |
| DIR-04 | P2 | 无案例空态 | “Create a case in Workbench” 跳转正常 |
| DIR-05 | P1 | 权限隔离：仅显示当前用户可访问的项目 | 与 access relay/隔离规则一致（commit 24ba9e0） |

## 6. TG-D DC Sizing —— Stage 1–3 业务核心（DC）

对应 `dc_view.py` 表单 + 冻结的 sizing core（`SIZING_LOGIC_CANON_V1.md`）。
业务分层：**Stage 1** POI 需求 → BOL/EOL 直流能量推导；**Stage 2** DC Block 选型与配置；
**Stage 3** 逐年 SOH/增容分析；Stage 4 打包输出给 AC。

### 6.1 输入控件逐项（DC-INP）

对每个数字输入执行四类检查：默认值合理、正常值可运行、min/max 边界值、非法值（负数/0/超范围/清空）不崩溃且有业务提示。

| ID | 控件 | 重点 |
| --- | --- | --- |
| DC-INP-01 | Project Name 文本框 | 预填 active case 上下文；改名后随 run 落库 |
| DC-INP-02 | POI Power (MW) | 0/负数拒绝；超大值（如 10000）行为；恢复 run 后回填 `[V1-回归]` |
| DC-INP-03 | POI Energy (MWh) | 同上；与 Power 推出的时长（如 2h）在结果中一致 |
| DC-INP-04 | Project Life (years) | 边界 1 年 / 上限；影响 Stage 3 年表长度 |
| DC-INP-05 | POI Nominal Voltage (kV) | 常用值 35/110/220；SLD 侧 MV 电压契约一致（`MV_RMU_VOLTAGE_CONTRACT_V2.md`） |
| DC-INP-06 | Frequency 下拉 (50/60 Hz) | 切换后随 run 持久化 |
| DC-INP-07 | Cycles per Year | 影响 Stage 3 SOH profile 匹配；边界值 1 / 730 |
| DC-INP-08 | Guarantee Year | 与 Project Life 的约束关系（不得超过） |
| DC-INP-09 | SC Time (months) | 0 与正常值 |
| DC-INP-10 | DoD (%) | 边界 1–100；百分数/小数容错（`to_frac`） |
| DC-INP-11 | DC RTE (%) | 同上 |
| DC-INP-12 | RTE Adjust (pp) | 正负调整生效方向正确 |
| DC-INP-13 | RTE Monotonic Enforce 勾选 | 勾/不勾时 Stage 3 年度 RTE 曲线单调性差异 |
| DC-INP-14 | Enable Hybrid 勾选 | 与 DC-INP-16 阈值联动（auto-toggle 逻辑 dc_view.py:769–792） |
| DC-INP-15 | Enable Cabinet Only 勾选 | 两个开关组合 4 种状态各跑一次 |
| DC-INP-16 | Hybrid Disable Threshold | 阈值跨越时 hybrid 开关自动联动、不死循环 |
| DC-INP-17 | POI is DC-side 勾选 | 勾选后 5 个效率字段的参与项变化 |
| DC-INP-18 | 效率字段 ×5（DC cables / PCS / MVT / AC SW / HVT） | 每项边界 90–100%；全部 100% 与默认值对比结果方向正确 |
| DC-INP-19 | Block Source 单选（radio dc_view.py:826） | 数据源切换后可运行且结果标注来源 |
| DC-INP-20 | Load Run：Run ID 文本框 + Load Run 按钮 | 有效 run 回填全部输入；无效 ID 明确报错不崩溃 |

### 6.2 运行与结果（DC-RUN）

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| DC-RUN-01 | P0 | 已知良好输入（400 MW/800 MWh）点击 Run Sizing | 成功产出结果，无 traceback |
| DC-RUN-02 | P0 | Stage 1 结果校验 | BOL/EOL 能量、可用能量推导与规格书一致（对照冻结 canon 的黄金值） |
| DC-RUN-03 | P0 | Stage 2 结果校验 | DC Block 型号、数量、container/cabinet 拆分正确 |
| DC-RUN-04 | P0 | Stage 3 年表（tabs 展示） | 年数 = Project Life；SOH 递减；增容年份与保证年逻辑一致 |
| DC-RUN-05 | P1 | Run 持久化 | Run Registry 出现新 run；Case working input 同步更新 `[V1-回归 FT-06]`；run 快照不可变 |
| DC-RUN-06 | P1 | 结果下载按钮（download_button dc_view.py:1442） | 文件可下载、内容非空 |
| DC-RUN-07 | P1 | CTA 按钮 “AC Sizing →” / “Single Line Diagram →” | 正确路由且携带 active run |
| DC-RUN-08 | P2 | 极小项目（如 5 MW/10 MWh）与极大项目（1000 MW+） | 成功或给出明确业务性拒绝（如无匹配 block） |
| DC-RUN-09 | P2 | 连续修改输入多次 Run | 每次生成独立 run；无 stale 状态串扰 |
| DC-RUN-10 | P1 | Guest 模式下 DC Sizing 可用性 | 按产品规则（可试算但受限持久化/导出）行为一致 |

## 7. TG-E AC Sizing（AC）

对应 `ac_view.py`。

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| AC-01 | P0 | 从恢复 run 打开 AC 页 | DC block 数、目标功率/能量正确带入（非 0）`[V1-回归 FT-01]` |
| AC-02 | P0 | AC Block Model 下拉恢复持久化选择 | 恢复保存的 model 或 legacy PCS 签名 `[V1-回归 FT-02]` |
| AC-03 | P0 | Run AC Sizing（已知良好 run） | AC Blocks=94、Model=`ACBLK-2X2500KW-20FT`、PCS/Block=2、PCS=2500 kW、Total=470.00 MW、无 `Insufficient power` |
| AC-04 | P1 | 自定义 PCS 数字输入 ×2（custom_col1/2） | 边界/非法值校验；计算联动正确 |
| AC-05 | P1 | 容器规则：单 AC Block ≤5 MW→20ft，>5 MW→40ft | `4×1250 kW=5 MW` 判为 20ft `[V1-回归 FT-04]` |
| AC-06 | P1 | 旧存档 `ACBLK-4X1250KW-40FT` 恢复 | 经 PCS 签名恢复为 20ft 等效 `[V1-回归 FT-04]` |
| AC-07 | P1 | 结果 trace 字段 | `ac_block_model_code/name/source/container_type/quantity_basis` 出现且合理 |
| AC-08 | P2 | 功率不足场景（人为小 DC 配置 + 大目标） | `Insufficient power` 业务提示而非崩溃 |
| AC-09 | P1 | AC 配置保存 | 保存后刷新/重进页面快照仍在 |
| AC-10 | P2 | 无 active run 直接进入 AC 页 | 明确引导，不崩溃 |

## 8. TG-F Single Line Diagram（SLD）

对应 `single_line_diagram_view.py` + readiness gate（`SLD_FORMAL_READINESS_GATE_V1.md`）。

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| SLD-01 | P0 | 从 active run 打开，确认数据源为 authoritative persisted mode | 页面明示数据来源 |
| SLD-02 | P1 | Run ID 文本框：改成无效/他人 run | 拒绝或明确报错 |
| SLD-03 | P1 | Group Index 下拉 | 各分组可切换渲染 |
| SLD-04 | P1 | Theme 下拉 dark/light | 两主题均正常渲染 |
| SLD-05 | P1 | Compact Mode / Draw Summary 勾选（4 组合） | 均无渲染错误 |
| SLD-06 | P1 | Renderer Mode 下拉 | 各模式生成成功；retired 模式不出现（`SLD_RENDERER_MODE_RETIREMENT_V2.md`） |
| SLD-07 | P1 | Override Mode 勾选 | 覆盖规则符合 `SLD_UI_OVERRIDE_RULES_V1.md`；关闭后回到默认 |
| SLD-08 | P1 | Plugin 下拉切换 | 各插件可生成 |
| SLD-09 | P0 | Generate SLD（按钮禁用逻辑：无 run 或无 AC 快照时禁用） | 禁用逻辑正确；生成后 artifacts 注册 |
| SLD-10 | P0 | 概念图内容红线 | 无 `1~2 BESS containers` 范围标注、无 `F3=0`/`F4=0` 悬空 PCS 文本 `[V1-回归]` |
| SLD-11 | P0 | Readiness gate | 未达 formal 就绪时输出保持 Concept / Not for Construction 水印 |
| SLD-12 | P1 | 下载按钮 ×4（SVG/PNG/JSON 等） | 全部可下载、文件后缀含 `.concept` 语义（对应 document_status） |
| SLD-13 | P1 | Clear Preview 按钮 | 预览清空、可重新生成 |
| SLD-14 | P1 | “Open Engineering Settings” 按钮 | 跳转正确并可返回 |
| SLD-15 | P1 | SLD Proposal Package V1：SLD-01/03/04 表单产物 | 生成、水印、issue 上限 6 条 + “... and N more” 指向 manifest |
| SLD-16 | P2 | AC 结果变更后重新生成 SLD | 图与最新 AC 快照一致，无陈旧缓存 |

## 9. TG-G Typical AC Block Arrangement + Site Constraint Set（ARR / CST）

对应 `site_layout_view.py`（页面已更名，导航保留 legacy alias）。

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| ARR-01 | P0 | 页面声明“非场地平面图/非施工图” | 文案存在 |
| ARR-02 | P1 | Block Index / Arrangement 下拉 | 各选项可生成 |
| ARR-03 | P1 | Show PCS&MVT SKID 勾选（无 AC 快照时禁用） | 禁用与显示逻辑正确 |
| ARR-04 | P0 | Generate 按钮（无 run/无 AC 快照禁用） | 生成 concept 产物；水印 `CONCEPT ONLY - NOT FOR CONSTRUCTION` |
| ARR-05 | P0 | 输出不得虚构 site boundary / access route / fire lane / POI routing / clearance | 逐项目视检查 |
| ARR-06 | P1 | 下载按钮 ×4 | 可下载、非空 |
| ARR-07 | P2 | Generate Prompt Payload + 两个下载 | payload 生成且内容与 run 对应 |
| ARR-08 | P2 | AI concept 上传（PNG/SVG）+ Submit + 审核下拉/Submit Review | 提交-审核闭环状态流转正确 |
| CST-01 | P0 | 未注册 Site Constraint Set 时 Master Layout 被锁 | 锁定提示明确 |
| CST-02 | P1 | 模板 download_button | 模板 JSON 可下载 |
| CST-03 | P1 | 上传不完整 JSON | 判为 `draft_incomplete` 持久化并有审计记录 |
| CST-04 | P1 | 上传完整 9 组输入 JSON → Register 按钮 | 注册成功、解锁条件之一达成 |
| CST-05 | P1 | `source_run.run_id` 指向其他 run 的 JSON | 注册被拒绝 |
| CST-06 | P2 | 超大 JSON 上传 | 记录行为（已知无大小上限，见状态文档 Deferred #2）——若无限制则记为改进项 |
| CST-07 | P2 | 每次 rerun 重复从 DB+磁盘加载（Deferred #1） | 观察性能，不作为缺陷，记录数据 |

## 10. TG-H 报告导出 / 工程设置 / 运行登记（RPT / ENG / RH）

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| RPT-01 | P0 | AC+SLD+Arrangement 齐备后打开 Report Export | 内容预览识别 DC / AC / SLD Image / Typical AC Block Arrangement (Concept Only) |
| RPT-02 | P1 | Report Template 下拉切换（含 Guoxia 变体） | 按钮文案与模板对应 |
| RPT-03 | P0 | Download Combined Report V2.1 | 下载成功、docx 可打开、Concept 边界保留在报告内 |
| RPT-04 | P1 | 部分产物缺失时导出（如无 SLD） | 预览如实反映缺失，报告不虚构章节 |
| RPT-05 | P2 | 连续两次导出 | 无状态污染 |
| ENG-01 | P1 | Engineering Settings 表单保存 | 保存成功、重进页面值保留 |
| ENG-02 | P1 | 设置变更对 SLD 生成的影响 | 与 `SLD_INPUT_CONTRACT_V1` 契约一致 |
| ENG-03 | P2 | “Go to Workbench” / “Go to Single Line Diagram” 跳转 | 路由正确 |
| RH-01 | P0 | Run Registry / Run History：Restore Run Inputs 按钮 | 恢复后路由到 DC Sizing 且输入可见 `[V1-回归 FT-05]` |
| RH-02 | P1 | 多 run 列表的完整性与排序 | 与 DB 一致 |
| RH-03 | P2 | 恢复历史 run 后再 Run | 生成新 run，历史 run 快照不变 |

## 11. TG-K Admin Portal（ADM）与 TG-L 平台级（PLAT）

### Admin Portal（Product & Database，49 个控件，按实体分节测试）

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| ADM-01 | P0 | Dashboard 打开，各实体计数显示 | 无 DuplicateWidgetID/render abort `[V1-回归]`；AC Block Templates 计数如实（当前 0） |
| ADM-02 | P1 | Cells 列表 + 编辑表单开合 | 每条记录 widget key 唯一（回归 819aa8d） |
| ADM-03 | P1 | DC Blocks / PCS / AC Blocks 各实体页切换 | 均可渲染 |
| ADM-04 | P1 | 编辑一条记录保存（在测试库上） | 落库成功、列表刷新正确 |
| ADM-05 | P2 | 新增/导入表单的空值与非法值 | 校验合理，不崩溃 |
| ADM-06 | P1 | 非 admin 用户访问 Admin Portal | 拒绝进入 |

### 平台级（PLAT）

| ID | P | 用例 | 预期 |
| --- | --- | --- | --- |
| PLAT-01 | P1 | 导航侧边栏全页面遍历（含 legacy alias “Site Layout”→新名） | 每页无 traceback |
| PLAT-02 | P1 | 页面间上下文一致性：任意页顶部的 project/case/run 上下文 | 与 active workspace 一致 |
| PLAT-03 | P1 | 浏览器刷新（F5）后会话与上下文 | 登录态与 workspace 恢复符合设计 |
| PLAT-04 | P2 | 双标签页并发操作同一账号 | 无数据损坏；行为可解释 |
| PLAT-05 | P1 | Alembic 迁移后启动（脚本路径） | `start_local_web.ps1` 流程健全 |
| PLAT-06 | P2 | Streamlit rerun 风暴（快速连续点击） | 无重复 run 落库、无死锁 |
| PLAT-07 | P2 | Arrow/dataframe 序列化回归（0e77ebb） | 各含表格页面无序列化报错 |

## 12. TG-M 预留章节 —— 未完成模块的未来测试挂点（FUT）

以下模块当前未开放或未完成，本章仅定义**测试挂点与解锁条件**，待功能落地后扩展为正式用例。

| ID | 模块 | 解锁条件 | 未来测试要点（预留） |
| --- | --- | --- | --- |
| FUT-01 | Concept Master Layout (P2) | 完整注册的 Site Constraint Set + 受控 footprint catalogue + 几何校验器 + rule basis（`SITE_CONSTRAINT_SET_V1.md`） | 几何确定性（同输入同输出）、边界/消防/检修通道合规、与 AC Block index 不做外推 |
| FUT-02 | SLD official（非 concept）签发 | formal readiness gate 全绿 | 水印移除条件、`.concept` 后缀退出、manifest 与 artifact hash 一致性 |
| FUT-03 | AC Block 产品库治理 | 业务确认 5/10 MW 模板（PCS 配置、LV 绕组、变压器 MVA、阻抗等） | AC Sizing 从简化下拉切换到治理产品记录后的等价性回归（94 blocks 黄金值不变） |
| FUT-04 | 主数据维护 API（`master_data_maintenance_api_prep.md`） | API 落地 | UI 与 API 双写一致性 |
| FUT-05 | 多用户 RBAC 细化（`AUTH_AND_RBAC_TARGET_MODEL.md`） | 目标模型实施 | 角色×页面×操作矩阵全遍历 |

## 13. 执行顺序（轮次）

1. **Round 0 — 环境准备**：快照测试库、跑全量 pytest、起 8599 隔离实例。
2. **Round 1 — P0 冒烟主业务流**（约 20 条）：AUTH-01 → WB-02/04/08 → DC-RUN-01~05 → AC-01/02/03 → SLD-09/10/11 → ARR-04/05 + CST-01 → RPT-01/03 → RH-01 → ADM-01。任何 S1/S2 阻断即停、修复、回归。
3. **Round 2 — P1 控件正确性**：各章 P1 用例，按页面顺序执行。
4. **Round 3 — P2/P3 边界与异常**：非法输入、空态、并发、超大值。
5. **Round 4 — 回归收口**：全部 `[V1-回归]` 用例 + 本轮修复项复测 + 全量 pytest。
6. 每轮结束更新第 14 章执行记录；全部完成后更新 `CURRENT_STATUS` 文档。

## 14. 执行记录（执行时填写）

| 轮次 | 日期 | 通过/失败/阻塞 | 新缺陷 | 备注 |
| --- | --- | --- | --- | --- |
| R0 | 2026-07-14 | 通过 | — | 快照 `_uitest_copy.sqlite`（旧副本备份为 `.prev-20260714`）；Alembic head；pytest 265 passed；8599 实例 HTTP 200；`uitest_admin` 重建 |
| R1 P0 冒烟 | 2026-07-14 | **全部通过**（清单见下） | FT-07 / FT-08 + 4 个观察项 | 无 S1/S2 |

### R1 P0 通过清单（2026-07-14）

- AUTH-01 登录；WB-01/02/04 三态引导与项目/案例创建；WB-06 项目切换；
  WB-08 恢复最新 run（路由 DC + 输入全回填）；WB-09 按钮禁用逻辑。
- DC-RUN-01~05（uitest 新案例，400 MW/800 MWh 2h）：Stage 1 理论需求
  916.18 MWh 与 canon 公式手算吻合；Stage 2 选型 185×5.016 MWh 容器；
  Stage 3 逐年 SOH 正常衰减（1.0→0.909@y5，POI 可用 804→558 MWh）；
  run 落库收敛（3 次迭代）；Case working input 同步更新（FT-06 回归 ✓）。
- AC（fresh run）：93 blocks / 465 MW 自洽；模型选择经 st.form 提交生效。
- AC-01/02/03（test-case 黄金回归）：DC 快照 188×20ft 非零（FT-01 ✓）；
  模型恢复 2×2500（FT-02 ✓）；重跑 94 blocks / 2 PCS / 470.00 MW ✓。
- SLD-01/09/10/11/12/15：authoritative persisted 数据源；strict 缺输入
  fail-fast 明确列缺项；Engineering Settings 保存后生成 concept 全套
  14 artifacts（`.concept` 后缀 + 水印 + readiness manifest）；SVG 红线
  检查干净（无范围标注/悬空 F3/F4/MISSING 泄漏）。
- ARR-01/04/05 + CST-01：非施工图声明；Master Layout 锁定（0/9 组）；
  concept 产物无虚构 site 元素。
- RPT-01/03：预览识别四项内容；V2.1 报告下载无错误。
- ENG-01/03：工程设置保存（source=Dedicated settings table）+ 历史记录。
- RH-01/02：Run Registry 28 条完整；details 内恢复按钮路由回填正确。
- ADM-01 + Cells/AC Blocks 切换：无 DuplicateWidgetID、无 traceback，
  AC Block Templates=0 如实显示。

### R1 新发现（除 FT-07 外）

- **FT-20260714-08（S4）**: Engineering Settings 页面渲染出 Streamlit 内部
  警告文本 “The widget with key `engineering_settings.rmu_rated_kv_derived`
  was created with a default value but also had its value set via the
  Session State API.” 应消除该 session-state 冲突。
- **OBS-01（R2 核查）**: AC 页 DC Snapshot 的 `POI ENERGY REQ.` 字段语义
  不一致——fresh run 显示 928 MWh（=DC 铭牌），test-case 旧 run 显示
  800 MWh（=POI 需求）。核查 `ac_view` 快照字段映射与新旧 run 持久化差异。
- **OBS-02（S4）**: Run Registry 表格数值未格式化（如 917.1048948725017）。
- **OBS-03（PLAT-03）**: WebSocket 重连后登录态丢失（Streamlit session_state
  特性）；工作区上下文本身持久正常。是否需要"记住登录"由业务决定。
- **OBS-04（待定性）**: 恢复历史 run 后 DC 页只回填输入、不展示旧结果面板；
  V1 口径只要求输入回填，需确认是否为设计意图。

### R1 视觉复核（真实 Chrome，2026-07-14）

应 Alex 要求切换到真实 Chrome（claude-in-chrome）复核界面显示完整性，
逐页截图确认：登录页、Workbench、DC Sizing（含 **POI Usable Energy by
Year 衰减图表正常显示**：y0≈800 贴红色需求线，逐年降至 y20≈558）、
AC Sizing（下拉选择一次成功；93 blocks/465 MW 结果卡片完整）、SLD
（专业图框 SLD-BESS-001、工程设置值入图 33kV/Dyn11/Uk7%/ONAN、CONCEPT
水印横贯、设备表为确定的 "2 BESS containers"）、Typical AC Block
Arrangement（DC Block+COOLING、PCS&MVT SKID、尺寸标注、水印）、Report
Export。**无界面显示不全问题**；此前的交互异常确认为嵌入式浏览器自动化
限制，非应用缺陷。逻辑层结论（DB/公式核对）不受浏览器影响，维持有效。

- 新增 **OBS-05**：重新登录后 project/case 上下文恢复，但 active run
  为 None、需显式 Restore（且未必等于上次会话最后使用的 project）——
  确认 workspace 持久化的更新时机是否符合预期。

### R2 进行中记录（2026-07-14）

- **FT-20260714-09（S3，已确认，待批量修复）— DC 输入无校验防线**：
  除 RTE Adjustment（-5~+2 pp）外全部数字输入未配置 min/max。端到端实测
  POI Power = **-400 MW** 被接受，产出 "DC POWER REQ = -413.49 MW"、92 容器
  的"成功"方案并落库，零报错。代码层核对：`poi_power/energy` 负值直通
  `to_float`；`dod_pct` 经 `to_frac` 不 clamp（150% 会低估需求）；效率字段
  同样无上限；仅 RTE effective 有 `clamp01`、S&C 有下限 3。修复方向与
  FT-07 合并为"输入验证守卫"（UI/pipeline 入口拒绝，不触碰冻结公式）。
- **FT-20260714-10（S2，已修复 ✓）— Run 后表单修改被静默还原**：
  每次成功 Run 后 `dc_view` 调用 `restore_run_bundle_to_session` 排队
  `_pending_dc_input_restore`；用户下次修改表单并提交时，
  `apply_pending_dc_input_restore()` 在控件实例化前用上次 run 的旧值覆盖
  全部 `dc_inputs.*` 键 → 新输入被静默丢弃、旧配置重跑并落库（用户以为
  跑的是新配置）。同一会话内首个 run 之后的所有参数迭代都受影响；
  登出重登（清空 pending）后第一次修改恢复正常——与实测证据链完全吻合。
  **Fix**: `restore_run_bundle_to_session` 新增 `queue_widget_restore`
  参数；post-run 刷新路径传 `False`（并清除残留 pending），显式恢复流程
  （Workbench/Run History/Load Run）保持原行为。回归测试
  `test_post_run_restore_does_not_stomp_next_form_edit`；全量 266 passed；
  浏览器端到端复测：Run(400/800) → 改 900 → Run 正确记录 400/900。
- **OBS-06（业务确认）**：从其他页面进入 DC Sizing 时表单显示全局默认
  （100/400）而非该 Case 的工作输入；仅显式 Restore 回填。是否应默认
  加载 Case working input 待定。
- 测试执行注意：`uitest-p0-case` 中的负功率/1C 垃圾 run 为 FT-09/FT-10
  取证数据（-400 系列、400/400 系列），勿作回归基线。

- **FT-20260714-11（S3，待修复）— 未收敛 run 无 UI 警示**：guarantee=25
  > life=20 时 pipeline 迭代 60 次增容仍 `converged=False` 落库，DC 页
  只显示"保存成功"，无任何未收敛警告（仅 Workbench 面板的 CONVERGED
  字段可见）。应在 DC 结果区显眼提示未收敛并给出原因。归入 FT-07/09
  输入守卫批量修复（guarantee ≤ life 校验 + 收敛状态提示）。
- **DC-INP-08 ✓（行为已记录）/ DC-INP-14 ✓**：hybrid 勾选后产出
  Hybrid/Container Only 双方案 tabs；hybrid 结果 184 容器 + 10 柜
  （尾差补柜恰好 ≤ K=10 busbar 上限），converged。
- **行为确认（非缺陷）**：`Disable Hybrid Threshold` 是 UI 默认推荐语义
  （容量超阈值时默认不勾 hybrid），用户显式勾选优先；pipeline 不强制禁用。
- **FT-10 修复后复测 ✓**：Run(400/800) → 改 900 → Run 记录 400/900；
  改 guarantee/hybrid 等后续迭代均正常生效。

### FT-07/09/11 输入守卫包 — 已实施并验证（2026-07-14，Alex 批准）

- 新增 `services/dc_input_guard_service.py`：
  1. **运行前** `validate_dc_inputs`（纯输入合理性，不复算 sizing 公式）：
     功率/容量 > 0、寿命 ≥ 1、循环 ≥ 1、guarantee ∈ [0, life]、S&C ≥ 0、
     DoD/RTE/五项效率 ∈ (0,100]（兼容百分数与小数写法）。违规 → 明确
     业务报错、不运行、不落库。
  2. **运行后持久化前** `validate_soh_curve_support`（数据驱动）：按
     pipeline 实际选中的 SOH profile 查曲线点数，< 2 点（占位曲线，如
     当前 1C 系列）→ 拒绝该模式并说明"产品库无该 C 率衰减曲线、无法
     支撑全寿命 sizing"，不展示误导结果、不落库。支持范围完全由产品库
     内容决定，未硬编码 C 率清单。
  3. **FT-11**：结果 tab 顶部对 `converged=False` 显示 NOT CONVERGED
     显眼警告（含迭代次数与处置指引）。
- 冻结核心零改动（仅 `ui/dc_view.py` 挂钩 + 新服务）；
  单元测试 `test_dc_input_guard_service.py`（12 条）；全量 **278 passed**。
- 浏览器端到端复测：-400 MW → 拒绝不落库 ✓；400/400（1C）→ 曲线库
  拒绝不落库 ✓；400/800（2h）→ 正常运行（916.18 MWh / 185 容器）✓。
- FT-07 / FT-09 / FT-11 状态改为 **已修复**。

### R2 后半段执行记录（2026-07-14 下午）

- **AC-04/05/08 ✓**：Custom AC Block 模型输入带 min/max 约束（1-6 台、
  1000-5000 kW，比 DC 表单规范）；Custom 3×2000 = 6.00 MW 正确判 40ft
  （>5 MW 规则）；总功率 558 MW 保存成功；功率不足场景（2×1500=279 MW
  < 400 MW）给出明确业务错误不崩溃。
- **FT-20260714-12（S3，已修复 ✓）— Custom 模型输入框不即时出现**：
  模型选择与 Custom 输入已移出 st.form（提交改为普通按钮），选择
  "Custom..." 立即显示配置项，无需盲跑。端到端复测通过。
- **FT-20260714-13（S3，已修复 ✓，Alex 判定）— 奇数 PCS 台数在工程上
  不可行**：分裂绕组变压器低压侧为双绕组，接不了 3 台 PCS；即使定制
  方案也不应允许。Custom PCS 台数从 number_input(1-6) 改为下拉
  {2, 4, 6}（偶数、可均分两个 LV 绕组），带工程原因帮助文案；残留的
  旧非法 session 值自动清理。端到端复测：下拉仅 2/4/6 ✓。此前用 3×2000
  生成的 SLD/run 属测试取证数据，不作基线。
- **SLD-04/05/08 ✓**：light 主题 + Compact + Draw Summary 组合生成正常；
  custom 6 MW 模型正确渲染为 3×2000 kW PCS + 6.7 MVA 三绕组变压器
  （1 MV + 2 LV secondaries，PCS 2+1 分配）+ 2 容器/块；水印保持。
  其余 renderer mode × plugin 全组合留 R3。
- **CST-02/03/04/05 全通过 ✓**：
  - schema_version 错误（`site_constraint_set_v1` vs 正确的
    `site_constraint_set.v1`）被明确拒绝（schema 防线生效）；
  - 不完整集（3/9 组）注册为 `draft_incomplete`，artifact
    `site_constraint_set.draft.json`；
  - run_id 不匹配注册被拒（明确报出两个 run id）；
  - 完整 9/9 注册为 `ready_for_constraint_validation`，artifact
    `site_constraint_set.ready.json`，且明示 "Master Layout renderer is
    not yet enabled"（P2 边界 / FUT-01 挂点保持）。
  - DB 版本化审计：两个状态的 artifacts 依次入库 ✓。
- **RPT-04 ✓**：未生成排布的 run，报告预览如实显示
  "○ Layout (not generated)"，不虚构章节。

**R2 剩余**：ADM-04/05（测试库上的编辑/新增保存）、Guest 模式
（AUTH-05/06/07、DC-RUN-10）、SLD renderer mode × plugin 全矩阵（并入
R3）。之后 R3 边界异常与 R4 回归收口。测试库中 3 个 1C run（e9150ca6/449bc681/a4d5fef9）为 FT-07
取证数据，勿作回归基线。浏览器自动化注意：Streamlit number_input 用 React
setter + input 事件 + blur 提交；表单内控件变更不即时触发 rerun 属正常。

### FT-20260714-07 — 1C 输入被静默接受并输出零衰减结果（S3，已确认为缺陷）

- **Symptom**: 输入 400 MW / 400 MWh（1C，1 小时系统）时 DC Sizing 正常收敛，
  Stage 3 逐年表 21 年 SOH 恒为 100%、POI 可用能量恒定不衰减；图表随之显示平线。
- **Root cause**: 主数据 `soh_curve_point` 中 `LFP314_1.0C_{365,540,730}cy` 三条
  曲线各只有 1 个占位点（year 0 = 100%）。Stage 3 按有效 C 率匹配到 1.0C profile
  后以唯一点持值外推，产出零衰减序列。2h 系统（匹配 0.5C 曲线，16–21 点完整
  数据）衰减正常（20 年 816.3 → 566.5 MWh），计算引擎与图表本身无缺陷。
- **业务判定（Alex, 2026-07-14）**: 支持什么系统由产品库曲线 + sizing 逻辑决定；
  库里没有 1C 曲线就无法做 sizing，必须严格执行最初业务逻辑——应当拒绝而非
  静默输出乐观结果。
- **Fix 方向（待批准后实施，S3 批量处理）**: 在 Stage 3 profile 选择处（或
  pipeline 入口）对曲线点数 < 2 的 profile 直接报业务错误并终止 run；因触及
  冻结 sizing core 边界，实施前需显式确认（`SIZING_LOGIC_CANON_V1.md` 允许
  新增校验、不允许改公式，此守卫属于"拒绝不可支撑输入"而非公式变更）。
- **测试纪律**: 在守卫落地前，所有测试输入保持时长 ≥ 2h（见测试点约定）。

## 15. 出口条件

- P0/P1 用例 100% 通过；P2 通过率 ≥ 90%，未通过项均有记录与处置决定。
- 无未关闭的 S1/S2 缺陷。
- 全量 pytest 通过（当前基线 246 tests）。
- FUT 章节挂点确认无误并保留。

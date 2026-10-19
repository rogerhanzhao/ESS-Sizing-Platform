# Report Export 统一流程修复（本地）

## 用户要求与原交互

用户明确要求保留原统一流程，不能为了适配cabinet增加一个报告生成步骤。

- DC页的`Export Technical Sizing Report`是原DC技术快报，直接下载，继续保留。
- 完整方案沿原DC → AC → Single Line Diagram → Typical AC Block Arrangement → Report Export推进，各页原底部Next Steps继续可用。
- Report Export原本自动准备文档，选Report Template后直接显示`Download Combined Report {brand.display_name}`。图纸在各自页面生成，报告页没有额外Generate/确认步骤。

## 已确认的问题及修复

柜组适配此前提前分派到新view，新增`Generate Cabinet Technical Proposal`，造成首次进入没有下载按钮；独立的`cabinet_report_brand`也绕开原模板状态。内部renderer分派被错误地呈现成了新的用户操作流程。

本轮仅调整报告页面交互和已有报告缓存判定，不改Sizing数学、旧SLD/报告renderer或原导航定义：

- 移除新增的生成按钮；页面验证来源后自动准备，直接提供原Combined Report主下载按钮。
- 统一使用`report_template_brand`，恢复Selected Run Summary、四项Report Content、Run references and data sources、Standard Product Information及Downloads区。
- 已验证的报告缓存直接复用；下载使用`on_click="ignore"`，点击下载不再重跑页面或写一份报告。
- 没有报告或同来源且完整、正常过期的报告可以自动准备。存储读取失败、结构缺失、来源/品牌/插件绑定错误、正文哈希损坏均明确停止并提供Retry，不能当缓存缺失覆盖。
- 当前AC子方案、DC年表、两份完整图包和品牌继续校验。不能跨父运行/兄弟方案/旧session找图，不在报告页暗中重生成SLD或布置图。
- 产品资料区沿用原数据库附件读取helper，仅查询；不自动上传/注册产品文件。
- 布置页针对柜组明确“预览一个AC Block，整包包含全部AC Block”；原集装箱分支继续保留one typical AC Block说明。

## 验证与发布边界

- 已对照HEAD原页面，并完成实现后两轮独立复核。旧`report_v2.py`与原5个SLD核心文件相对HEAD均无差异。
- 新增6项真实Streamlit AppTest，验证首次直接下载、缓存命中、共享模板与白标、源包异常及缓存读取异常/恢复后重试。报告服务14项含新9项损坏缓存边界，专项通过。
- 最终完整回归`1001 passed in 379.55s`，日志`output/unified_report_flow_20261018/final-test-suite.log`，退出0。compileall与git diff --check通过。较早的992项为追加缓存边界测试前的检查点，不能替代最终回归。
- 真实网页：48柜DC页原快报实际下载；沿DC→AC→SLD（切第2页）→布置→Report Export进入，无Generate步骤。CALB Combined Report实际下载与前轮10页文件SHA-256一致，且数据库报告记录更新时间、字节及DC/AC运行数均未改变。
- 首次选择Guoxia模板后自动准备并直接下载，白标审计通过。仅增加该品牌的DOCX及manifest两条附件，不新建DC/AC运行。
- 真实网页恢复100MW/400MWh、92台集装箱历史方案，原Combined Report下载按钮直接可用，已实际下载；原本未生成图纸的情况继续显示原缺图说明，未改成柜组流程或强制出图。
- 浏览器页面及前后数据库只读快照均保存在`output/unified_report_flow_20261018/`，当前阶段DC运行数18、AC运行数11。
- 从集装箱方案再返回48柜方案，直接下载的CALB文件仍与初始文件完全相同；`after_guoxia_first.json`与`after_final.json`完全一致，已有报告内容和更新时间没有被重写。最终页面留在48柜CALB Combined Report下载处，截图`final-direct-download-page.png`，汇总验收`acceptance.json`。

本轮只在本地隔离数据库及127.0.0.1:8511验证。没有Git提交、GitHub推送或生产部署。

## 2026年10月19日通用按钮名称

用户明确要求按钮不体现配置产品细节。两条报告分支已统一为`Download Technical Proposal`，替代前文原Combined Report标签；仍直接下载，不增加生成步骤。模板、实际文件命名及原报告生成逻辑保持，UI及冻结保护专项13项通过。此命名要求取代本文此前的具体按钮文案，不改变统一交互要求。

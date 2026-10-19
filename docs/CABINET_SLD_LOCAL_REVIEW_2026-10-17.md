# Cabinet SLD V1 — 本地受控增量

状态：本地实现与验证；概念图，不是正式电气设计。本轮不推送或部署。

## 保留的原链路

原 Single Line Diagram 页面在已有 AC 快照解析、运行/项目/算例校验后，仅对 dc_unit_kind=independent_cabinet_group 路由至新控件。普通集装箱及 mixed head-fleet 继续原有工程图渲染器、规范输入、就绪度和附件路径。旧图面/拓扑基线不更新。

原 sld_pipeline_service、ac_to_sld_adapter、sld_engineering_v2_renderer、sld_authoritative_builder、artifact_service 五文件本轮前后 SHA-256 一致。冻结公式不动。

## 新模块职责

- calb_diagrams/cabinet_sld.py：只接受已保存柜组对象，校验柜号/容量/PCS/AC数量及镜像分配，生成每AC Block一张SVG及独立拓扑图数据。
- services/cabinet_sld_service.py：SVG转PNG、完整ZIP、概念就绪度manifest；复用既有persist_artifacts和DiagramArtifactBundle。注册前核对输入与所选AC子方案的快照完全一致。
- ui/cabinet_sld_view.py：原页面内选择预览AC Block、生成、缩放、下载、刷新恢复，继续既有下一步导航。

## 接线与证据边界

每柜按保存编号画在自己组内，共用该组独立DC母线；一组只接一PCS，独立组之间不画直流联络。2绕组采用共用LV母线；3绕组画独立LV-A/LV-B，PCS分配明确为概念分配、待OEM确认，不画联络。只有选择了确认拓扑的数据才出图。每组1..12柜适用当前受控418kWh产品。

所有图面及附件metadata固定CONCEPT / NOT FOR CONSTRUCTION。没有型号、向量组、保护、接地、阻抗或电流证据的地方为TBC，不套用20ft DC箱额定值。电压注明AC输入依据；PCS铭牌功率不是净POI保证。原已选变压器结构不等于OEM PCS分配已确认。

## 保存与恢复

正式账号必须有当前DC下面已选的AC子方案，写入该子方案；访客只有会话预览，零附件注册。恢复只查所选子方案，include_ancestors=False，不读DC父运行、其他AC方案或latest平面文件。manifest包含输入签名、版本、柜组合同、来源DC/AC、每页文件哈希及拓扑。签名/结构/哈希不符拒绝恢复。最新仅SVG生成时忽略以前遗留PNG。10月18日改为校验同一完整包后直接切页，下文保留首轮清理旧预览的历史测试记录。

## 输出

网页选择一张AC Block作预览，SVG/PNG为当前页；ZIP包含该方案所有AC Blocks的SVG/PNG及manifest。刷新后从确切AC子方案恢复上次所选页。旧正式报告仍保持柜组专用闸门，尚不因此宣称完整报告或实际布局已适配。

## 验证

已通过35项新渲染器测试，含48柜4组、41柜尾组、1 PCS和8 PCS、三绕组隔离、错误映射拒绝、文字转义与确定性、几何文本边界；6项包/持久化测试，含跨方案/父级回退拒绝、修改字节拒绝、访客不写、SVG-only旧PNG隔离；3项新UI测试，含选页清理及权限失败友好提示。既有SLD相关回归56项通过，含旧图面/拓扑、模式隔离、访客、权威来源、附件归属及冻结守卫。

完整回归及真人浏览器生成/刷新验证结果将在下文补充。

## 最终本地回归与网页验收

- 首轮完整873 passed；补充历史DC运行对应AC子方案恢复用例后，最终875 passed（272.66秒）。编译通过。
- 旧56项SLD相关专项回归通过，原5个核心文件校验值不变。独立审查未发现遗留P0/P1。
- 真实Chrome从Workbench恢复13:35历史48柜DC运行，沿原入口进入SLD；精确匹配其保存AC子方案后显示柜图控件，无需重算AC。
- 网页生成第1张并注册4类concept附件；PNG下载到D:/Users/Download/cabinet_sld_ac_001.concept.png，与数据库附件SHA-256一致。
- 切AC Block 2时旧预览清除；生成后确认SVG仅含C025至C048，不含C001。ZIP含该方案两张SVG/PNG及manifest。
- 完整刷新恢复检查另记；当前仍未提交、推送或更新生产。

## 完整刷新恢复确认

真实Chrome整页刷新并重新登录后，恢复同一13:35历史DC运行，再进入SLD，自动匹配原AC子方案；未点击Generate即恢复上次AC Block 2、预览PNG、四个下载按钮及下一步导航。图面为C025..C048，恢复caption明确来自当前AC方案。浏览器截图cabinet-sld-restored-browser.png；实际完整PNG为cabinet-sld-48cab-ac2.png，完整ZIP为cabinet-sld-48cab-sheets.concept.zip。

最终875项全量通过；git diff --check通过；原5个核心文件SHA-256不变。本地服务维持运行，用户浏览器已登录留在柜组SLD页面。没有提交、GitHub推送或生产更新。

## 10月18日后续本地修正

- 切换AC Block不再要求重新Generate。先验证当前方案的原始manifest、完整ZIP成员集合及所有内容哈希，再读取目标页；访客使用相同纯内存选择流程。切页不渲染、不写库，也不改变原ZIP/manifest字节。共享预览及单页下载随当前页更新；元数据分别保留当前预览页与原生成选择。
- 只在输入比较和签名中排除顶层source_ac_run_id（每次运行随机变化的会话token）。真实数据库AC子方案ID、DC父ID、所有实际参数及柜组映射继续参与校验。不能由此跨方案或跨DC恢复。
- 原生成选择仍是完整刷新后的默认预览；临时切页不伪装成重新生成或注册。柜组输出版本提升至1.0.1，原本地1.0.0图需重新生成一次，不能绕过旧签名强制复用。
- 新柜图的LV端口文字移到变压器框外，修复双PCS图的标题碰撞；接线保持。原集装箱SLD核心文件保持。
- 本轮完整回归893 passed（230.01秒）；新渲染器36项、服务22项、UI4项，旧SLD专项56项通过。compileall与git diff --check通过，原5个核心文件SHA-256不变。物理布局与正式柜组报告仍待专用适配，不能据此视为整包发布完成。
- 后续报告接入须明确整包选页：数据库通用SLD附件仍是Generate时选择的页，临时预览切页只更新会话中的共享图包，不重写数据库。不得把原manifest的selected_ac_block当作用户当前预览选择，也不得绕过现有柜组报告闸门直接沿用DB-first旧报告流程。
- 真实Chrome：Generate第1页后直接切第2页，四个下载按钮及预览保留；实际下载cabinet_sld_ac_002.concept.svg，含C025..C048且不含C001，与完整ZIP第2页字节一致。相同AC参数再次Run显示unchanged、仍1个alternative，返回SLD未点击Generate即可恢复。布局、报告下一步入口可进入，均保留明确的专用适配未完成提示。
- 只读数据库核对：15条DC运行、该DC下1个AC子方案、该AC下4类柜图附件；两页均能恢复。证据sld-followup-verification.json；PNG/SVG/全页ZIP已更新至1.0.1。没有提交、推送或生产更新。
- 最后整页刷新并重新登录，Restore Latest Run恢复同一48柜DC，进入SLD未点击Generate即显示默认第1页及四类下载；随后直接切第2页，图纸和下载保持。当前本地页面留在该柜组方案供用户继续测试。

## 后续布置图及技术报告进展

2026-10-18已接入柜组专用概念Block Arrangement与技术DOCX导出，沿用原页面流程；完整图包来源、全部AC Block覆盖及刷新恢复已验证。安装尺寸及距离的源文件正文仍不可读，有尺寸安装设计未完成。最终986项回归通过，细节以`CABINET_ARRANGEMENT_REPORT_LOCAL_REVIEW_2026-10-18.md`为准；前文待适配描述为当时检查状态。本轮仍未提交、推送或部署。

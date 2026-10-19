# 柜组布置与技术方案报告 本地验证

状态：本地柜组概念布置与技术方案报告已完成并验证，尚未提交、推送或部署。保留 DC → AC → SLD → Typical AC Block Arrangement → Report Export 原页面流。这里的完成不包含有尺寸的安装设计、施工图或正式性能保证。

## 范围与数据来源

- 新柜组布置适用于已批准的 independent_cabinet_group 合同，保留每组实际柜号、容量及一组一 PCS 对应。独立新绘图器不调用旧集装箱布置器，也不修改冻结计算。
- 布置图为相对位置与设备分区概念图，不按比例，不计算占地。设备/服务/电缆/变压器MV预留区不代表已经确认的物理尺寸或消防分区。
- 技术报告严格读取持久化 DC case_input、Stage1/2/3 以及选中 AC 子方案；不从 Excel defaults、可编辑 case 当前值或旧会话推回输入。年表原值直接复制，不重选衰减曲线、不计算第二套 Sizing。
- 图纸只来自所选 AC 子方案的完整包，校验来源、版本、全部成员及哈希。无父运行、兄弟方案或 latest 平面文件回退。报告包含每个实际 AC Block 的 SLD 与布置图，不受当前预览页选择影响。

## 新模块职责

- calb_diagrams/cabinet_arrangement.py：纯概念布置、分组与安装证据结构验证；复用柜组 SLD 的合同门禁，坐标仅为图面排版。
- services/cabinet_document_service.py：柜组文档的严格已保存 AC 来源与签名边界。
- services/cabinet_arrangement_service.py：整包生成、PNG/SVG、清单、注册、校验恢复与无写库选页。
- services/cabinet_report_data_service.py：已保存 DC/AC 对齐并生成报告数据，包含情景、数量、产品、输入、年表及非有限值检查。
- services/cabinet_report_service.py：读取两份完整同源图包，生成报告指纹、注册与恢复，按品牌分别保存报告。
- reporting/cabinet_report.py：纯 DOCX 内容、品牌与图文排版。正文纵向，完整图纸附录 A3 横向。白标先清理 SVG 再光栅化，最终执行品牌泄漏审计。
- ui/cabinet_document_context.py、cabinet_arrangement_view.py、cabinet_report_view.py：原页面中的权限、选页、生成、下载与导航。原报告对柜组提前路由，避免经过旧图纸回退链。

## 安装证据边界

用户指定长期产品资料入口：D:/OneDrive - CALB/CALB-Documentation sharing V1.0 - 文档/DC Block，当前418子目录418KWh-Product-UL。

已定位用户手册、2026-7-13 Datasheet、UL 9540A单元/模组报告、UL 9540 Listing Report及NFPA69报告。初次读取均为OneDrive占位文件，Windows正文读取错误为cloud sync network unavailable；用户已启动同步，正文尚未验证。文件名和目录不能视为证书/间距结论。

installation_basis支持 documented/unverified、柜体尺寸及独立dimension_source、逐项距离/关系/证据类别/来源页/适用条件。测试布置值必须明确 TEST SETUP / NOT INSTALLATION MINIMUM；厂家要求单独标记。documented尺寸必须有文档标题和正整数页码；不能仅凭status把数值升级为厂家依据。当前网页没有注入未核验尺寸/距离。

## 报告与存储

- 保留绝对SOH与相对COD的SOH区别，百分比两位小数。模型POI能量与PCS铭牌功率分开，不声明净POI功率保证。
- 可读方案名称使用原AC Alternative A/B规则，不向客户文档打印UUID或本地路径。
- 不连续柜号按实际连续子段列出，不能用min..max暗示中间所有柜子属于该组。
- 布置完整ZIP及manifest为图纸真源；通用layout_png/svg仅为当前页便利导出。技术报告及其manifest按品牌保存在同一AC子方案。
- 页面刷新可恢复已保存图包/报告，真实输入、源包或品牌变化使旧报告失效。游客只可内存布置预览，不开放报告下载。

## 验证记录

### 最终完整回归与原链路保护

- 2026-10-18最终完整回归：`986 passed in 263.80s`（执行会话90831，完整日志`output/local_web_20261017_human/final-test-suite.log`）。此前检查点为986项/290.89秒；柜组SLD阶段的875/893项记录仍保留在原阶段文档，不替代本轮验证。
- 原5个SLD核心文件前后未变：`services/sld_pipeline_service.py`、`adapters/ac_to_sld_adapter.py`、`calb_diagrams/sld_engineering_v2_renderer.py`、`services/sld_authoritative_builder.py`、`services/artifact_service.py`。新柜组路径沿用原页面和所选AC子方案，未修改冻结Sizing公式或旧集装箱绘图逻辑。
- 本轮网页及下载验证前后，本地隔离库的DC运行数保持18、AC运行数保持11。选页、恢复和技术报告导出未额外创建DC/AC方案。

### 实际网页、下载与报告排版

- 已从本地实际网页核对柜组布置与技术报告的生成、下载及恢复；使用当前保存的DC结果和对应AC子方案，未以仅单元测试通过替代网页验收。
- 技术报告的10页渲染已逐页核对。报告保留纵向正文及完整A3横向图纸，包含全部实际AC Block的SLD和布置图；当前预览哪一页不改变报告图纸覆盖范围。
- 已保存年表按原数据输出，百分比显示两位小数；相对SOH、绝对SOH、模型POI能量和PCS铭牌功率分别表达。客户文档不打印内部UUID或本地源路径。
- 技术报告版本1.0.1移除封面继承的标题装饰线及可能残留旧情景名称的系统Case code，改列实际Independent cabinet groups。源代码与源数据仍保留在内部指纹中。
- 最终网页下载文件为`output/local_web_20261017_human/CALB_Cabinet_Technical_Proposal_48Cab.concept.docx`，SHA-256为`6f348cbbfe1d26d542f5639030a3e4550df5fb2ae8974a2356dc2f8efb064f07`。最终10页渲染在`cabinet-report-render-final/`，逐页完成视觉核对。
- 整页刷新、重新登录、Restore Latest Run后，沿DC页面底部进入SLD再进入Report Export；未点击Generate即可恢复下载，第二次下载与前次字节完全相同。布置图亦在重新登录后直接恢复预览与四类下载。截图`cabinet-report-restored-browser.png`、`cabinet-arrangement-restored-browser.png`。

### 安装源资料仍待正文可读

- 用户已启动OneDrive同步。本轮独立核验对UL9540A unit报告、用户手册及Datasheet各读取一次：均可读取文件元数据，但正文读取失败，未获得可核对的PDF页码或关键页图像。
- 核验记录：`output/418_installation_evidence_20261018/independent-probe.json`。本次错误为`OSError [Errno 22] Invalid argument`；未重试，未调整网络或文件同步状态。早先的cloud sync network unavailable记录保留为当时状态，不据此推定当前网络状态。
- 用户再次要求继续后，17:47本地时间对相同3份文件各读取一次，正文仍不可读；新增记录`output/418_installation_evidence_20261018/probe-current.json`，未更改源文件或同步设置。
- 因此，柜体尺寸、安装距离及测试摆放条件仍未验证。文件名、占位文件大小、已有默认值均不能作为安装依据；当前交付保持概念布置及明确的TBC边界。

本轮没有Git提交、GitHub推送或生产部署。本地验证完成不等于发布批准，后续仍需用户本地确认及受控发布检查。

## 后续统一下载流程纠正

用户指出额外Generate Report步骤不符合原统一流程。该步骤已移除，恢复原Report Template及Download Combined Report交互；缓存损坏与正常过期分开处理。最终后续回归1001项通过。详见`REPORT_EXPORT_UNIFIED_FLOW_REVIEW_2026-10-18.md`；本文件前文986项属于布置/报告初次接入阶段。

# 柜组技术方案实际导出审阅

审阅对象：用户提供的`D:/Users/Download/CALB_test_BESS_Proposal_20261019_V2.2_Cabinet.concept.docx`，SHA-256 `a6f3f0de705c11036f8c5d9f825576be6e4c0eb3cbe932d6f8798c609e05173d`。已提取正文/年表、检查目录链接并渲染查看全部10页。

## 范围与本轮实际修改

用户再次明确：原纯5MWh DC Block从Sizing到方案导出的逻辑不得修改；仅允许不合理制图及页面规范优化。

初次审阅未修改报告正文、图纸和Sizing结果，仅把两个配置分支的合并方案下载按钮统一为`Download Technical Proposal`。随后用户明确要求柜组技术方案沿用原报告架构，本地柜组导出器已按下述九章结构调整；原5MWh导出器、文件命名与统一直接下载流程保留。

旧`report_v2.py`、原5个SLD核心及7个冻结计算模块已相对HEAD核对无差异；冻结模块固定哈希全部匹配。

## 逐页发现与建议

| 页码 | 已验证的呈现问题 | 建议范围 |
|---|---|---|
| 1 | 封面突出48柜与20.064MWh，POI 8MW/16MWh和第4年校核结果要翻页才清楚；目录9个链接有效但无可见页码 | 仅新柜组报告增加简洁方案摘要，区分需求、装机与模型结果；补目录页码/图号 |
| 2 | Operating frequency实际是cycles/year，而POI frequency才是Hz；94%输入RTE与年表93.10%缺紧邻解释 | 区分Cycling frequency / Grid frequency；明确输入RTE与年度模型RTE为两个字段，不改任何值 |
| 3–4 | 相对SOH100%与绝对SOH98%基准不同；年4只是4 G，客户不易一眼识别；20年分析周期可能被读成20年均保证16MWh | 表头完整说明SOH参照，突出第4年评估行，明确16.16MWh对应年4，年5为15.88MWh、年20为12.27MWh；分析周期不等于逐年合同保证 |
| 5 | 4台PCS合计8MW为铭牌功率，不能把它与8MW POI需求相同解读成净POI已验证；清单缺显眼合计 | 可加已有数据合计/状态摘要；保留净功率需验证的边界，不重选PCS或重算损耗 |
| 6、8 | 两组支路集中在上方，SLD中部大片留白；柜号嵌入后约6.9pt，偏小 | 只优化新cabinet SLD少组版的坐标、行距、柜框和字号；目标柜号约9pt。连接、数量、柜号映射不动 |
| 7、9 | 布置图柜号约11.3pt，分组和PCS对应清楚，无裁切/碰撞；页脚有内部renderer/contract标识 | 保留布局结构，内部标识移至manifest，客户页使用简短图号。不得补造尺寸、安装间距或占地 |
| 10及全篇 | 说明与限制在封面、曲线、表注、图脚、末章重复；Caption普遍小号粗体，视觉权重偏大；页眉为软件Beta报告名称 | 仅新柜组报告统一页眉/图号/标题层级，精简重复文案，普通注释用正常字重；概念状态与必要适用边界保留 |

四张工程图嵌入图像均为3000×2121px，主要问题是源码字号和固定画框布局，不是先提高导出分辨率。四幅图分别正确覆盖C001–C024与C025–C048，未发现漏柜、截断或额外空白页。

## 不得为排版一致而修改的技术点

- DOD95%、20.064MWh铭牌、相对SOH与绝对SOH两套参照、原年度能量与RTE全部保留。
- effective DC rate0.412C与所选SOH/RTE曲线0.330C是报告保存的不同字段。这里只建议解释选用依据，不能为了数值看起来一致而重选曲线、插值或覆盖值。
- 输入DC RTE94%与年度RTE93.10%等值不能互相覆盖。
- S&C原始字段暂无明确Shipping/Storage英文展开依据，不自行改为FAT-to-COD或其他未验证含义。
- 图纸继续为CONCEPT / NOT FOR CONSTRUCTION；没有已验证原文时，不发布安装最小间距或合规判断。

## 当前纯5MWh页面来源核验

用户截图运行后缀`ba9d012e`已核对为100MW/400MWh、container_only、92台5.016MWh集装箱、0柜。对应AC与图纸来自原容器插件。实际在用户Chrome页面下载`CALB_test_BESS_Proposal_20261019_V2.2.docx`，正文为92 DC Blocks、23 AC Blocks、4×1250kW/块、461.472MWh，未出现柜组报告标题。按钮同名不能用于判定生成器或配置来源。

另在只读来源审查中确认旧legacy图缓存清理及回退归属存在待专项复核的缺口，但新柜组正常路径不写这些旧缓存，当前完整容器图纸也没有发现错误来源。本轮未擅自重构原报告数据链，问题与当前通用按钮命名分开记录。

本轮仅本地操作，未提交、推送或部署。

## 柜组报告架构对齐（后续执行）

以实际原5MWh下载文件`output/cabinet_report_review_20261019/current-container-download.docx`及原`report_v2.py`的工程主线为参考，仅调整`reporting/cabinet_report.py`：

1. Executive Summary：区分POI需求、DC装机、PCS铭牌及指定年份模型能量。
2. Project Inputs & Assumptions：原项目输入、循环频次与电网频率分别列明。
3. Stage 1 DC Energy Sizing：直接复制保存的理论DC能量、功率、S&C损耗及效率链，不重算。
4. Stage 2 DC Block Configuration：柜体产品清单及实际独立柜组→PCS连接表。
5. Stage 3 Lifetime Degradation & POI Deliverable：原曲线及完整年表，突出指定评估年，明确两种SOH基准。
6. Stage 4 AC Block Sizing：真实AC Block设备分配与PCS合计。
7. Single Line Diagram：集中列出所有实际AC Block的已验证柜组SLD。
8. Typical AC Block Arrangement：对应全部实际AC Block的原柜组概念布置图。
9. Concept Site Arrangement：列已知边界、依据与待确认资料，不套用容器占地/距离或构造新场地图。

输出样稿为`output/cabinet_report_review_20261019/CALB_Cabinet_Technical_Proposal_Aligned.concept.docx`，共13页，含4张A3图。初次渲染发现两页孤立章标题，已仅收紧A3章标题段落后重渲染，最终13页全部查看。原用户DOCX的SHA-256未变；21行年度数值、柜体产品、4个柜组映射与原AC设备行逐项一致。目录9个链接均指向有效书签，4个A3页均含真实图像。

柜组报告插件版本升为`1.1.1`，使旧版完整缓存按既有签名机制自动重建；读取失败/跨方案/哈希异常仍按原机制阻止导出。没有另加生成报告步骤。专项检查90项通过；最终完整回归1008项通过，耗时227.31秒，记录见`output/cabinet_report_review_20261019/full-regression.log`。初次全量中的3项失败均为旧测试仍查找旧下载按钮名称，已同步为用户要求的通用英文按钮后重跑全部通过；未放宽图纸读取失败的阻断规则。

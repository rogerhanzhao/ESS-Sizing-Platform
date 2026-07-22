# Session Handoff — 2026-07-16 ~ 07-18（报告治理 + 排布知识库 + Layout L1）

交接对象：任何后续执行者（Claude / Codex / 人工）。开工前必读：
1. `CURRENT_STATUS_2026-07-12.md`（导航规则与模块地图；§2.2 指向本轮产出）
2. `AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md`（产品与排布知识基线，owner 定案）
3. `LAYOUT_ROADMAP_V1_2026-07-18.md`（L1→L2→L3 路线；L1 已完成）

---

## 1. 本轮已完成并合入 master 分支线（ops/ubuntu-docker-coexist-20260311）

| 提交 | 内容 | 状态 |
|---|---|---|
| `4396902` | 报告 V2.1 客户可读性整改：恢复 Stage-3 里程碑柱状图（DC/POI 双色 + 目标线）、公式错字 DIscharke→discharge、Meets-Target 仅保证年评估、封面/页码页脚/表格样式（蓝头斑马纹右对齐）、PCS 枚举折叠、空页压缩 | 已部署 |
| `e66cc11` | 品牌集中化：`reporting/brand_profiles.py`（CALB_BRAND/GUOXIA_BRAND 并排、无散落默认值）；Guoxia 白标不再泄漏 CALB（封面落款/保密声明）；双品牌 GUOXIA-LOGO2 页眉；设备名中性化（CALB_5MWh→5MWh）；logo 缺失阻断导出；7 个品牌分离回归测试（解包 docx XML 断言） | 已部署 |
| `c628b8c`+`db4fc8a` | 知识库 + 概念渲染器入库（docs/concept/），整场排布修订为 MV 居中镜像 | 文档 |
| `bcecdff` | Layout Roadmap V1 | 文档 |
| `cfd309b` | **L1 完成**：`calb_diagrams/ac_block_arrangement_v2.py` 引擎 + 报告 §8 规则版排布图与规范依据表 + 9 个几何测试 | 部署中（见 §3） |

测试基线：**311 passed**（`python -m pytest tests/ -x -q`，~40 s）。

## 2. 关键 owner 决定（不可回退，违反即返工）

- 排布设计基准 = **国际标准**（IFC/NFPA 855/NFPA 850/UL 9540A），不用 GB；
  间距只能来自 `ArrangementRuleProfile`（US 默认 0.30/3.0/0.9 m），**禁止硬编码 2.0 m**。
- DC 箱镜像背靠背成对（门朝外），**顶部泄爆板在无门背板侧**；端面风机格栅靠门侧、
  控制柜靠背侧；液冷段窄镂空。全部细节见知识库 §2。
- PCS+MV = 20 ft 一体舱（Sineng EH / NR PCS-9567MV-5000 级），报告图内**品牌中性**。
- 整场：同排两 AC Block 镜像、MV 站朝中央共用 2.0 m 中压走廊、馈线单向至变电站；
  2×DC 与 4×DC 双规格可混排。
- 报告品牌文案只能来自 BrandProfile（两 profile 并排在 brand_profiles.py）；
  新增文案必须两个 profile 同时加，品牌分离测试会拦截泄漏。

## 3. 进行中 / 立即待办

0. ~~待部署 `2cb294c`（§8 规则版主图）~~ **已部署（2026-07-18）**：服务器运行
   `ce97c9b`，HTTP 200，报告 §8 现为单一规则版图。注：本机在内网时 SSH 可直连
   `calb-server`（无需 VPN）；GitHub 出口仍不通，发布走 relay。
1. ~~服务器部署~~ **已完成（2026-07-18）**：服务器运行 `4d23c6b`，HTTP 200。
   注意：服务器→GitHub 443 出口再次回退（TLS reset/timeout），`calb-serverctl.sh update`
   的 pull 会失败——**当前发布用 relay 流程**（见 runbook，已补部署记录）。
   每次发布前可先试直连，失败即走 relay，勿在直连上反复重试浪费时间。
2. **L2（下一开发项）**：`services/site_array_concept_service.py` + 报告新增 §9，
   规格见 Roadmap §2-L2；参考几何在 docs/concept 渲染器第三视图。
3. L1 尾项（可选）：UI "Typical AC Block Arrangement" 页接入 V2 引擎替换旧画法；
   轴测示意图（Python 版）待做。

## 4. 环境与流程速查

- 服务器：`ssh calb-server`（172.16.1.141，需 VPN）；应用 `/opt/calb-sizingtool/app`，
  Docker 单容器，18511→8501；EnerGain 三容器共存勿动。
- 发布：本地测试 → push GitHub → 服务器 `calb-serverctl.sh update`（内部 ff-only pull +
  rebuild + restart）→ HTTP 200 验证 → runbook 记录。断网备用：relay 流程见 runbook。
- 报告验证：`tools/regress_export.run_dc_sizing/run_ac_sizing` + `build_report_context` +
  `export_report_v2_1`（模式见 tests/test_report_v2_smoke.py）；Word COM 转 PDF 逐页目检。
- sizing core 仍冻结（SIZING_LOGIC_CANON_V1）。
- 效果图交付物：artifact https://claude.ai/code/artifact/e2d16a95-7224-4d5c-8543-ef4e1b140432
  与 `D:\Users\Download\AC_Block_Concept_Package\`（本地 PNG+HTML 包）。

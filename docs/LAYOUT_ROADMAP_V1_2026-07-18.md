# Layout Roadmap V1 —— SLD 之后的排布工作路线（2026-07-18）

本文档承接 `AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md`（产品与规范知识基线）与
`CURRENT_STATUS_2026-07-12.md` §3 的 P2 边界，记录 owner 已定案的排布方案，并规划
SLD 之后 Layout 域（AC Block / DC Block 组合排布 + 整场排布）如何落进平台与导出报告。

---

## 1. 已定案方案（owner 2026-07-18 确认，后续实现以此为准）

### 1.1 AC Block 单元排布（两种规格，均为定案）

```
2×DC AC Block（5 MW / 10.03 MWh）           4×DC AC Block（5 MW / 20.06 MWh）
┌─────────┐ 3.0m ┌─────────┐               ┌────┐0.9m┌────┐ 3.0m ┌─────────┐
│ DC 镜像对 │◄───►│ PCS&MV 站 │               │DC对│◄──►│DC对│◄────►│ PCS&MV 站 │
│ 0.30m 背靠│      │ 20ft 一体舱│              └────┘    └────┘      └─────────┘
└─────────┘      └─────────┘               包络 ≈22.07 × 5.18 m
包络 ≈15.12 × 5.18 m
```
- DC 对：镜像背靠背 0.30 m（UL 9540A 豁免口径）；门侧朝外（检修通道）。
- DC↔MV 站通道 3.0 m（10 ft，NFPA 850 油浸设备）；干变/特批市场可参数化收窄。
- PCS & MV 站：20 ft 一体舱（Sineng EH / NR PCS-9567MV-5000 级），690 V→34.5 kV。

### 1.2 整场排布（owner 修订定案：中压布线便利优先 + NFPA 合规）

- **同排两个 AC Block 左右镜像，MV 站一律朝场地中央**，两站之间留 **2.0 m 中压走廊**；
  RMU 馈线在走廊汇集后**单方向**敷设至道路侧，沿消防车道至变电站/汇集点。
  ⚠️ 禁止一排内全部同向（MV 出线分散、电缆绕远）。
- 2×DC 与 4×DC 规格可混排，各排共用同一条中压走廊中线。
- 排与排之间 6.0 m（20 ft）消防车道（环通或尽端回车）；门侧检修通道 3.0 m；
  车道端消火栓；围栏 + 大门；Remote-location（>100 ft）选址优先。
- 参考实现（视觉与几何基准）：`docs/concept/ac_block_concept_render.html` 第三视图。

---

## 2. 路线图：三个阶段

### Phase L1 —— AC Block Arrangement V2（单元级，先行）
**目标**：把概念渲染器的单元级几何移植为平台 Python 模块，替换现有
"Typical AC Block Arrangement" 页的简化画法。

- 新模块：`calb_diagrams/ac_block_arrangement_v2.py`（纯几何+SVG，无 UI 依赖），
  输入 = Run 数据（AC:DC 配比、DC 数、AC Block 模板、market rule profile），
  输出 = 平面图 + 轴测示意（SVG/PNG artifact，走现有 artifact 管线）。
- **Rule profile 参数化**（本轮研究的核心结论）：
  `ArrangementRuleProfile { market: US_NFPA | CN_GB(备查) | EU_AHJ,
  dc_pair_gap, dc_to_mv_aisle, pair_to_pair_gap, mvt_type: oil|dry }`
  ——US_NFPA 默认：0.30 / 3.0 / 0.9 m；禁止硬编码 2.0 m。
- 外观遵守知识库 §2（泄爆板无门侧、液冷段、端面列位、标识位置）。
- 测试：几何断言（间距=Profile 值、镜像对称、包络尺寸）+ SVG 基线回归
  （沿用 validate_rendered_sld_svg 的质量门模式）。

### Phase L2 —— Site Array Concept（整场概念排布）
**目标**：把 §1.2 定案规则做成整场生成器，输出"概念整场排布图"。
**不是 Master Layout**：不落真实场地边界，`document_status=concept` 水印强制。

- 新服务：`services/site_array_concept_service.py`：
  输入 = AC Block 总数（来自 sizing）、单元规格（2/4 DC）、rule profile、
  可选行数/长宽比偏好；算法 = 镜像成对 → 行 → 中压走廊对齐 → 消防车道/围栏包络；
  输出 = 场地包络尺寸估算 + 整场鸟瞰 SVG + 中压走廊/车道清单。
- 若已注册完整 Site Constraint Set（P2 门槛件），可读取边界多边形做
  "能否放下 N 行"的粗校核并给出告警——但**几何裁场仍留给 P3**。
- 测试：N 块→行列分配正确性、走廊居中对齐、NFPA 间距、包络公式。

### Phase L3 —— Concept Master Layout（即原 P2 边界，不变）
按 `CURRENT_STATUS` §3 与 `SITE_CONSTRAINT_SET_V1.md`：注册完整场地约束集 +
受控设备足迹库 + 确定性几何校验器 + 明确 rule basis 之后，L1/L2 引擎作为其
构件在真实边界内布置。本路线图不提前解锁该边界。

---

## 3. 导出 SIZING 报告集成（V2.1 报告）

| 报告位置 | 内容 | 数据源 | 阶段 |
|---|---|---|---|
| §8 Typical AC Block Arrangement（升级） | L1 平面 + 轴测两图、Rule profile 表（间距及其规范依据 NFPA 850/UL 9540A）、单元包络尺寸 | Run + ArrangementRuleProfile | L1 |
| §9（新增）Concept Site Arrangement | 整场鸟瞰图、AC Block 数/行列分配、场地包络估算表、中压走廊说明、"CONCEPT ONLY" 水印与免责句 | sizing 结果 + site_array_concept_service | L2 |
| Executive Summary 补一行 | Site envelope (concept) ≈ W × D m | 同上 | L2 |

- 出图走 `document_status` 三态治理（正式版仍禁 Master Layout 图纸）。
- BrandProfile 兼容：图内不落厂商字样（Sineng/NR 仅作产品级依据写入知识库，
  报告图为中性 "PCS & MV Station"），白标变体无需另做图。
- 回归：报告含新章节后更新 docx 结构测试与品牌分离测试。

## 4. 实施顺序建议
1. L1 模块 + §8 报告升级（一个迭代可完成；SLD 域测试模式可复用）。
2. L2 服务 + §9 报告新增（含 concept 水印治理）。
3. 渲染器（docs/concept）继续作为视觉规范参照；照片级 3D 为独立课题，
   不阻塞 L1/L2。

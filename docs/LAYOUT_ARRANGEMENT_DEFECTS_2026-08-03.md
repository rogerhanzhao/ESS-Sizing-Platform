# Layout / Arrangement 缺陷审查与优化方案（2026-08-03）

**触发**：owner 审阅导出报告 `CALB_test_BESS_Proposal_20260803_V2.1.docx` 后指出
第 8 章（Typical AC Block Arrangement）与第 9 章（Concept Site Arrangement）
"没有按照产品的尺寸和规范来布置"。

**被审报告的配置（取自该报告 §6 表格，属事实基准）**

| 项 | 值 |
|---|---|
| AC Block Template | 8 × 1250 kW |
| AC Block Size | **10.00 MW** |
| PCS per AC Block | 8（每块 8 条馈线） |
| DC Blocks Total | **100** |
| AC Blocks Total | **13** |
| Transformer (per block) | 11.11 MVA |

即该站就是受管产品 **`ACBLK-10MW-8PCS-8DC-40FT-BILATERAL`** 的形态：
**40 ft AC Block + 双侧 4+4 DC 场**。

**权威依据**
- `docs/AC_BLOCK_PRODUCT_KNOWLEDGE_2026-07-18.md` §1.2 / §4 / §5（owner 定版）
- `calb_sizing_tool/schemas/governed_ac_block_config.py`（配置代号即含 `40FT`）
- `calb_diagrams/ac_block_bilateral_layout.py`（已实现 40 ft 站的双侧引擎）
- 同行现场观察：知识文档 §6（LinkedIn：MaxSolar×Sungrow / CATL TENER /
  Tesla Megapack —— 排内紧贴、门侧统一朝检修面、排间大通道）

---

## 一、已确认缺陷

### F1 — PCS & MV Station 尺寸被硬编码为 20 ft，40 ft 产品被画成 20 ft ❌

`calb_diagrams/ac_block_arrangement_v2.py`

```python
MV_LENGTH_M = 6.058     # 20 ft ISO —— 与 AC Block 容量无关，恒定
MV_WIDTH_M  = 2.438
```

- 知识文档 §4：**5 MW = 20 ft 一体舱**；更大容量为 **Sineng EH-12500
  （40 ft 旗舰，32×组串 PCS + 13750 kVA 油浸变）**。
- 本报告是 **10 MW / 8 PCS** 的 AC Block，站体应为 **40 ft = 12.192 m**。

| | 报告实际 | 应为 |
|---|---|---|
| 8×DC AC Block 包络 | **35.99 × 5.18 m** | **42.12 × 5.18 m** |
| 站体长度 | 6.058 m（20 ft） | 12.192 m（40 ft） |

**少画了 6.13 m 站体长度。** 这正是 owner 所指"40 尺 AC Block 不能是 20 尺的尺寸"。

> 注：双侧引擎 `ac_block_bilateral_layout.py` **已经正确使用 40 ft**
> （provisional note: `40 ft station 12.192x2.438 m uses nominal ISO dimensions`）。
> 缺陷只存在于 §8 走的这条 **rule-based 线性** 路径。

### F2 — §9 站阵列把每块功率/每 DC 能量写死，报告自相矛盾 2 倍 ❌

`calb_diagrams/site_array_concept.py`

```python
_BLOCK_POWER_MW = 5.0      # 硬编码
_DC_ENERGY_MWH  = 5.015    # 硬编码
...
total_power_mw  = n_blocks * _BLOCK_POWER_MW
total_energy_mwh= n_blocks * dc_per_block * _DC_ENERGY_MWH
```

| | 报告 §9 图/图注 | 报告 §6 事实 |
|---|---|---|
| 每块功率 | 5 MW | **10.00 MW** |
| 全场功率 | **65 MW** | **130 MW** |
| DC 块数（算能量用） | 13 × 8 = **104** | **100** |

**同一份报告里 §9 的功率是 §6 的一半**，且能量按 104 块算而实际 100 块。
这是可直接被客户发现的硬伤。

### F3 — 10 MW/8-DC 产品被按"线性 4 对一排"绘制，而非受管的双侧 4+4 ❌

- 受管产品的物理形态是 **中央竖置 40 ft AC Block + 西 4-DC / 东 4-DC 镜像场**
  （`central_40ft_bilateral_4plus4`，包络 **18.79 × 13.02 m**）。
- 报告 §8 走的是 `render_ac_block_plan_svg` 线性路径，画成 **一排 4 组镜像对
  + 端部站体**（35.99 × 5.18 m）——细长带状，与产品实物形态不符。
- 触发原因：本次是**通用运行**（非受管运行），`ctx.layout_variant` 为空，
  `report_v2.py` 的 `is_bilateral` 判定为 False，因而落到线性分支。
  → **判定只看 `layout_variant`，不看实际的 8 PCS / 8 DC 形态。**

---

## 二、DC Block 四面净距定则（owner 2026-08-03 定版）

| 面 | 说明 | 净距 |
|---|---|---|
| 门面（6 个立门） | 朝检修通道 | **3.0 m** |
| 无门宽面 | 镜像对背靠背 | **0.30 m** |
| **设备端**（液冷机组 + 风机格栅） | 与 AC Block 通道同口径 | **3.0 m** |
| **设备端相反的另一端** | 0.9 / 0.3 皆可，取优先值 | **0.9 m** |

→ 现状 `pair_to_pair_gap_m=0.9` 统一用于相邻镜像对之间，**未区分端面朝向**。
按上表，若相邻两对之间出现**设备端**，该处应为 **3.0 m** 而非 0.9 m。
此项并入 P0-1 一并实现。

## 三、优化方案

### P0-1 修 F1：站体尺寸按 AC Block 型号解析，不再硬编码
1. 在 `ArrangementRuleProfile` 之外引入 **station spec**（长/宽/形态），
   由 **AC Block 型号/PCS 数/功率** 解析：
   - ≤ 5 MW（≤4 PCS）→ 20 ft 一体舱 6.058 × 2.438 m
   - ≥ 10 MW（8 PCS）→ **40 ft 12.192 × 2.438 m**
2. `compute_layout()` 增参 `station_length_m`（默认按上述解析），
   包络公式改为 `dc_span + aisle + station_length_m`。
3. **与 `ac_block_bilateral_layout.py` 共用同一套 ISO 尺寸常量**，
   避免两条路径再次各写各的（本次缺陷的根因就是两处不共享）。
4. 站体形态（撬块式/一体舱）按知识文档 §8-3 预留枚举，本次只做尺寸。

### P0-2 修 F2：站阵列的功率/能量必须来自真实 Run
1. 删除 `_BLOCK_POWER_MW` / `_DC_ENERGY_MWH` 两个硬编码常量。
2. `compute_site_array()` 增加必填参数
   `block_power_mw`、`dc_block_energy_mwh`、`dc_blocks_total`，
   由 `report_v2` 从 `ctx`（AC Sizing / DC Sizing 结果）传入。
3. 能量用**真实 DC 块总数**（100），不再用 `n_blocks × dc_per_block`（104）。
4. 加**跨章一致性断言**：§9 图注的 MW/MWh 必须等于 §6 表格值，
   不一致即在报告校验里报错（沿用既有 `_validate_report_consistency` 机制）。

### P1-3 修 F3：按实际形态选择排布引擎，而非只看 `layout_variant`
1. `report_v2` 的 `is_bilateral` 判定改为：
   `layout_variant == BILATERAL` **或**（`pcs_per_block == 8` 且 `dc_per_ac == 8`）。
2. 通用运行落到 8PCS/8DC 时，也走双侧 4+4 引擎（图注仍标 Concept / 假定）。
3. 若两者都不满足，才回退线性引擎。

### P1-4 防回归
- 为 F1/F2 各加一条**数值断言测试**：
  - 8×DC + 10 MW → 包络宽度 ≈ 42.12 m 且站体 = 12.192 m；
  - §9 图注功率/能量 == §6 表格功率/能量（跨章一致性）。
- 把"**站体尺寸/每块功率/每 DC 能量一律不得硬编码**"写入布局模块的模块级注释。

### 执行顺序建议
`P0-2`（报告自相矛盾，客户可见，改动最小且零风险）
→ `P0-1`（尺寸修正，需同步基线）
→ `P1-3`（引擎选择，影响图形形态，需 owner 看图确认）
→ `P1-4`（回归锁定）

---

## 四、影响面

| 模块 | 改动 |
|---|---|
| `calb_diagrams/ac_block_arrangement_v2.py` | 站体尺寸参数化（F1） |
| `calb_diagrams/site_array_concept.py` | 删硬编码、改签名（F2） |
| `calb_sizing_tool/reporting/report_v2.py` | 传真实功率/能量；引擎选择判定（F2/F3） |
| `tests/` + SLD/报告基线 | 新增断言、重生成基线 |

**不涉及**：DC/AC sizing 计算本身（`ac_sizing_service.py` 等冻结模块不动），
电气拓扑与 SLD 单线图逻辑不动。

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

## 二之二、8 台 DC 的排布：四面环绕已被否决，定版为一字型（owner 2026-08-03 二次定版）

**过程如实记录。** 先按 owner 的第一版指示"当一个 AC Block 配置 8 台 DC Block 时，
可以将 DC Block 不止在 AC Block 左右两侧"实现了 `compute_quad_layout()`
（`QUAD_LAYOUT_VARIANT`，N/W/E/S 各一个镜像对，18.79 × 28.54 m / 536 m²），
出图送审。**owner 看图后否决**：

> "不能搞环绕布置，第二张图可以，要考虑后序的整站布置，所以请重新设计一下 …
> 按一字型排"

### 否决理由（记录下来，防止再次被"重新发明"）

1. **多两条 3.0 m 通道**：536 m² vs 双侧 4+4 当时的 284 m²，多占约 **252 m²（+89%）**。
   （双侧方案随后按 F8 把设备端朝外，包络降到 18.79 × 13.02 m / **244.6 m²**，差距更大。）
2. **南北两对的直流电缆要绕过站体**，比左右两侧长得多。
3. **破坏整站排布**：整站是把 AC Block 沿**一条轴**排成行、行间走消防道
   （知识文档 §5）。环绕型在南北两侧凸出，行与行之间无法紧密排列。

### 定版方案

**一字型（single-axis）**：西 4-DC 场 │ 3.0 m 通道 │ 中央竖置 40 ft AC Block │
3.0 m 通道 │ 东 4-DC 场 —— 全部落在**同一条东西轴**上，站体南北两侧不放任何设备。
这与 2026-07-24 已确认的 `central_40ft_bilateral_4plus4`（每侧 2×2 `田` 字场）
**是同一个几何**，无需改动受管配置代号。

| 方案 | 包络 | 占地 | 结论 |
|---|---|---|---|
| 线性一排（8 台一字排开） | 48.42 × 5.18 m | 251 m² | 2026-07-24 已否决，勿复活 |
| **一字型双侧 4+4（定版）** | **18.79 × 13.02 m** | **244.6 m²** | 最省地、电缆最短、可成行 |
| 四面环绕 | 18.79 × 28.54 m | 536 m² | **2026-08-03 否决，已删除** |

### 落实

- `compute_quad_layout()` / `QUAD_LAYOUT_VARIANT` **已从代码库删除**；
  `tests/unit/test_ac_block_bilateral_layout.py::test_perimeter_field_is_gone_and_must_not_come_back`
  用 `hasattr` 锁住，防止回归。
- `report_v2` §8 的引擎选择不再分叉：**受管运行与通用 8PCS/8DC 运行画同一张图**
  （一个产品，一个几何）。

## 二之二之二、以"综合整站占地面积最小"为目标的复核（owner 2026-08-03 三次指示）

> "无论整张还是 typic ac block arrangement，都要考虑综合整站占地面积最小"

### 先把度量口径纠正过来：**包络面积 ≠ 占地面积**

单块的设备包络会骗人。把每块**摊到整站**（相邻块共用的净距只算一次）后算
"每块 AC Block 实际吃掉多少地"：

| 方案 | 东西周期 | 南北周期 | 每块占地 | 每台 DC | 设备占比 |
|---|---|---|---|---|---|
| **A 双侧 4+4，中央竖置站体（现方案）** | 21.79 | 16.02 | **349.0 m²** | **43.6** | **42.4%** |
| B 一字长带 48 m，中央横置站体 | 47.22 | 8.18 | 386.1 m² | 48.3 | 38.3% |
| C 2×4 立式场，站体在端部 | 13.61 | 32.03 | 436.1 m² | 54.5 | 33.9% |
| D 4 对排成一排，站体另起一条带 | 32.70 | 15.40 | 503.5 m² | 62.9 | 29.4% |
| （参考）纯 DC 场理论下限，不含站体 | — | — | 261.9 m² | 32.7 | — |

**结论 1：一字长带（B）的单块包络更小（250.6 vs 284.0 m²），整站占地却更大
（386 vs 349 m²，+11%）。** 因为它 5.18 m 深却要南北各留 3.0 m 门通道，
通道与设备之比高达 37%（A 只有 19%）。**所以上一轮"改成 48 m 一字长带"的想法
如果做了，是把地占大——现方案 A 已经是这几种里的最小值。**

**结论 2：站体开销是硬的。** 2.438 m 宽的站体要塞进净距序列，最少多吃
`2.438 + 3.0 = 5.438 m`（占掉一条既有通道 + 新开一条），这条省不掉。
A 已经做到了这个下限（349 − 261.9 = 87.1 m² = 5.438 × 16.02）。

### F8 — 设备端朝向没有建模，白白多占约 10% 的地 ❌

DC Block **两端不对称**：设备端（液冷 + 风机格栅）要 3.0 m，另一端只要 0.9 m。
原代码把两端合并成 `max(pair_to_pair, dc_equipment_end) = 3.0`，**每一处端面间隙
都按 3.0 算**，等于假设集装箱两端一样。

正确做法：**让每隔一台调头**，把要 3.0 m 的**设备端朝向块的外边界**——那里整站
本来就必须留 ≥3.0 m 的检修通道（否则人进不去）——把只要 0.9 m 的**平端留在块内部**。

| | 块内间隙 | 块边界 | 块包络 | 行间距 |
|---|---|---|---|---|
| 原（设备端朝内） | 3.0 | 0.9 | 18.79 × **15.116** | 15.116 + 3.0 = 18.116 |
| **改（设备端朝外）** | **0.9** | 3.0（由通道提供） | 18.79 × **13.016** | 13.016 + 3.0 = **16.016** |

行间距少 **2.1 m**，而块边界那 3.0 m 是**本来就要留的通道**，等于白拿。

**实测整站节省（2 块/行 + 组间消防道模型）**

| AC Block 数 | 原占地 | 改后占地 | 节省 |
|---|---|---|---|
| 4 | 2 062 m² | 1 870 m² | 9.3% |
| 8 | 3 713 m² | 3 330 m² | 10.3% |
| **13（本报告）** | **6 327 m²** | **5 657 m²** | **10.6%** |
| 20 | 8 941 m² | 7 847 m² | 12.2% |
| 40 | 17 472 m² | 15 421 m² | 11.7% |
| 80 | 34 670 m² | 30 568 m² | 11.8% |

线性引擎同理：8-DC 的块端面间隙由 `3.0/3.0/3.0 = 9.0` 变成 `0.9/3.0/0.9 = 4.8`，
包络 **48.424 → 44.224 m**（每块少 4.2 m）。

**落实**：新增 `end_gap_sequence()` / `unit_offsets_m()`；
`EquipmentPlacement.equipment_end` 记录哪一端是设备端；图上把液冷/风机格栅
画成百叶带，看图就知道哪端是设备端（以前默认对称，读图的人无从判断）。

### F9 — 分组行数写死 `ceil(bpg/2)`，多修消防道 ❌

`rows_per_group = ceil(blocks_per_group / 2)` **与块的实际进深无关**。
浅进深的块本可以一组多排几行，却被切成更多组，**每多一组就多一条 6.0 m 消防道
横贯全站**。

**修复**：`_max_rows_per_group()` 按 IFC §503.1.1 的
`fire_access_limit_m`（45.7 m）和**实际块进深**把组填满；
owner 显式给的 `blocks_per_group` 只能把它**收紧**，不能放宽。
例：14 块 × 2-DC，原来切 2 组多一条消防道，现在 1 组、0 条内部消防道，
可达距离 27.1 m «45.7 m。

### F10 — 占地面积从来没被报出来过 ❌

"占地最小"是目标，就必须**可度量**。`SiteArrayLayout` 新增
`land_area_m2` / `land_per_block_m2` / `land_per_mwh_m2`，
报告 §9 表格新增 **Site land area** 与 **Land intensity**（m²/AC Block、m²/MWh），
§8 图注补上包络面积。

## 二之二之三、整站（"无论整张"）的复核 — 第二轮

上一轮把**块**压到了最小，但**整站**那一半只做了一半：8PCS/8DC 的报告根本没有 §9
（引擎画不了中央站体的块），而站级模型里还有三条没查过的假设。这一轮补上。

### F11 — 消防道是**断头路**，互不连通 ❌（既是合规问题，也扭曲了占地账）

`render_site_svg` 只画东西向的道路，**没有任何南北向连接**，也没有场地出入口。
消防车开进任何一条路都出不去，也到不了另一条。IFC §503.2.5 对超长尽端路要求回车场，
标准做法是**环形道**。

**连带后果**：原模型只在**上下两条边**收 6.0 m 道路成本，左右只收 3.0 m 净距，
于是**又长又窄的场地显得特别便宜**——搜索出来的"最优"是 24.8 × 223.2 m（长宽比 9:1），
这是模型假象，不是真优化。

**修复**：四周画**环形消防道**（6.0 m），内部组间道路两端接入环道。
`perimeter_clear_m` 不再叠加（6.0 m 道路已经大于 3.0 m 净距，叠加是虚报占地）。

> **占地数字会变大，这是纠正少算，不是变差。** 13 块站：5 657 → 6 526 m²。
> 之前那个数少算了环道。

### F12 — 每行块数写死为 2，大站白丢最多 10.5% ❌

`per_row` 恒取 2。场地是矩形，**道路和围界成本随周长走**，所以让场地接近方形的
"每行块数"才便宜。写死 2 对小站正好，对大站就亏。

**修复**：`plan_site_packing()` 在满足消防可达距离的前提下**搜索**每行块数。

| AC Block 数 | 固定 2/行 | 搜索最优 | 最优每行 | 节省 |
|---|---|---|---|---|
| 4 / 8 / 13 | 2 157 / 3 842 / 6 526 m² | 同左 | **2** | 0%（小站本来就最优） |
| 20 | 9 052 m² | 8 566 m² | 4 | 5.4% |
| 26 | 11 736 m² | 11 612 m² | 3 | 1.1% |
| 40 | 17 789 m² | 16 330 m² | 8 | 8.2% |
| 80 | 35 262 m² | 31 560 m² | 8 | **10.5%** |

### F13 — 中央站体的块整站画不出来，§9 直接没有 ❌

L2 引擎只能从 `dc_per_block` **反推**一个线性块，所以 8PCS/8DC（本报告的形态）
要么被抑制、要么被画成它不是的东西。上一轮我选了抑制 + 出文字，**等于没做"整张"**。

**修复**：新增 `BlockForm`，可携带块的**真实 placements**；站级图元直接画它们。
`mirrorable` 区分两类块：站体在行端的块可以两两镜像共用 2.0 m MV 走廊；
**中央站体的块不行**（对外四面全是 DC 门面和设备端），块间要留满 3.0 m 检修通道。
现在 §9 画的就是 §8 画的那个块。

**本报告（13 块 / 130 MW / 521.6 MWh）**：2 块/行 × 7 行，2 组 1 条内部消防道，
**52.58 × 124.11 m = 6 526 m²**，即 **502 m²/AC Block · 12.5 m²/MWh**。

### 站级两种块形的对比（连通环道模型）

| N | 中央站体块（18.79×13.02） | 线性块（44.22×5.18） | 中央站体块优势 |
|---|---|---|---|
| 13 | **6 526 m²** | 6 651 m² | −1.9% |
| 26 | **11 612 m²** | 12 118 m² | −4.2% |
| 40 | **16 330 m²** | 17 780 m² | −8.2% |

**中央站体块在站级每个规模都赢**，再次印证块形选择正确。

### F14 — 报出来的占地数字必须说清楚不含什么 ❌

现在报占地了，客户会拿它当征地面积。必须写明：
**这是环形道以内的设备 + 通道用地，不含升压站、运维楼、堆场、雨水设施和退界。**
图注和 §9 表格都加了这句。

## 二之二之四、"报告与页面必须一致"的收口（owner 2026-08-03 四次指示）

> "无论是导出的报告还是页面展示的 typical ac block arrangement 都要一致的
> 逻辑排布和绘制"

### 先取证，不先下结论

把同一个 run 的两条路径各渲一张 SVG 逐行 diff。结果：**几何、图元、标注全部一致，
只差 5 行** —— 标题文字（`TYPICAL AC BLOCK 1` vs `TYPICAL AC BLOCK`）和页面多打的
一层水印 `<g id="calb-document-status">`。

**但这不等于安全。** 真正的问题是**同一套规则被写了两遍**：

| 决策 | 报告里的实现 | 页面里的实现 |
|---|---|---|
| 用哪个引擎 | `layout_variant == BILATERAL or (pcs==8 and dc==8)` | `pcs_count == 8 and dc_blocks_total == 8` |
| 图怎么起标题 | `configuration_code or "TYPICAL AC BLOCK · …"` | `ac_block_model_name or "TYPICAL AC BLOCK {i} · …"` |
| 本块功率/站体等级 | `_site_nameplate_from_ctx()` | `pcs_count × pcs_kw or block_size_mw` |
| DC 台数怎么数 | `dc_blocks_total // ac_blocks_total` | `dc_allocation_plan[block_index]` |

**四条规则各写两遍 = 四个漂移入口**，而"一个产品两个尺寸"正是本文档从头到尾在修的
那条缺陷链。今天一样，不代表明天一样。

### F15 — 排布规则被实现两遍 ❌

**修复**：新增 `calb_diagrams/typical_ac_block_arrangement.py`，**唯一入口**
`render_typical_ac_block(shape, profile)`，它拥有：

- `uses_central_station()` —— **唯一**的引擎选择规则；
- `block_label()` —— **唯一**的标题规则；
- `resolve_dc_blocks_for_block()` / `resolve_pcs_for_block()` /
  `resolve_block_power_mw()` —— **唯一**的取数规则（按块取，不取全场平均：
  混合站里 tail 块 PCS 少、功率小、站体等级也可能不同）；
- `apply_concept_watermark()` / `strip_document_status()` —— **唯一**的水印实现。

报告 §8 和页面插件现在都**只做一件事**：从各自的数据源解析出 `AcBlockShape`，
然后调这一个函数。`report_v2._uses_central_station_block()` 也改为委托同一条规则，
所以 **§8 / §9 / 页面三处再也不可能对"这块该用哪个引擎"有分歧**。

> **各自保留的部分**：从哪里读这块的形状。报告读 `ReportContext`，页面读用户选中
> 那一块的 `AcSnapshot`。这个差异是**真实且应有的**——形状是输入，排布不是。

### F16 — 页面的渲染器下拉框还能选到旧栅格引擎 ❌

页面把 `layout_engineering_v1`（无规范出处的旧栅格）和规则引擎并列在下拉框里。
**用户选前者，页面就又和报告不一致了** —— 一个能产生分歧的选择器，正是这次要消灭的。

**修复**：页面只提供规则引擎（`ARRANGEMENT_PLUGIN_ID`，在 `layout_service` 里
单点定义，页面和服务不可能各写一个）。旧插件仍注册着，供程序化调用和既有测试使用，
但页面不再暴露。同时删掉 `2x2 / 1x4 / 4x1` 与手填净距控件——规则引擎不理它们。

### 水印为什么允许不同

页面**直接把 SVG 交出去**，所以水印打在 SVG 上；报告**先栅格化再打**，走的是
fail-closed 的 `_stamp_not_for_construction`（本文件前面那条 P1 缺陷修的就是它）。
**同一个标记，不同介质**，两边都不能少。一致性测试用
`strip_document_status()` 把这层剥掉再比，比的是**图**，不是标记。

### 回归锁 — `tests/unit/test_typical_ac_block_arrangement.py`

- `test_report_and_page_emit_the_identical_drawing` —— 剥掉水印后
  **逐字节相等**（8PCS/8DC 与 4PCS/4DC 两种形态各一条）；
- `test_neither_surface_reimplements_the_engine_rule` —— 用 `inspect.getsource`
  确认两边都走 `render_typical_ac_block`，且**旧的 `pcs==8 and dc==8` 硬判定
  不会再出现在任何一侧**；
- 另有引擎规则、标题规则、取数规则、水印可逆性、fail-closed 的独立断言。

### 端到端核对（真实导出）

| | 报告 §8 | 页面 |
|---|---|---|
| 标题 | `TYPICAL AC BLOCK 1 · 8 PCS / 8 DC · 40 FT CENTRAL STATION` | 同左 |
| 包络 | 18.79 × 13.02 m（245 m²） | 18.79 × 13.016 m（244.6 m²） |
| 引擎 | `central_40ft_bilateral_4plus4` | 同左 |

## 二之二之五、全面复审（owner "请再次审核一遍！！！ 全面的"，2026-08-04）

**不是复述已做的事，是去找已做的事里的错。** 做法：不看 happy path，
用**11 组真实形态的 run** 把报告和页面两条路径各渲一次逐字节比对；
再对站级模型做参数矩阵扫描。查出 **6 个真缺陷**，全部已修并加锁。

### F17 — 页面认 `ac_block_model_name`，报告不认 ❌

通用运行如果绑定了产品名，**页面标题写产品名，报告写生成的描述**。
两张图标题不同 = 客户会以为是两个东西。

### F18 — 受管变体的键名两边读的不是同一个 ❌

报告读 `layout_variant`，页面读 `ac_block_arrangement`。`ac_view` 今天两个都写，
所以**碰巧一致**；只写一个的写入方一出现就会分裂。而且形态已经是 8/8 时这个分歧
被完全掩盖 —— **会带着缺陷发版而没人发现**。

### F19 — 没有分配计划的 run，页面硬报错、报告照画 ❌

同一个 run，一边出图一边报错。

> **F17/F18/F19 的共同根因**：上一轮我把引擎选择、标题、绘制收敛了，
> **却把"怎么读这个 run"留在两边各写一份**。收敛得不彻底 = 没收敛。
> 现在 `ac_block_shape_from_ac_output()` 是唯一的形状解析入口；
> 报告只保留一个有文档的 override（混合站画 head 块）。

### F20 — `blocks_per_group` 不再是"块"的意思 ❌

`rows_per_group = ceil(blocks_per_group / 2)` 里的 `2` 是"每行 2 块"的硬编码。
F12 让每行块数变成搜索出来的以后，**这条换算就错了**：
声明上限 8 实际排出 20 块一组。
修复：按**实际每行块数**换算，且用 **floor 不是 ceil**（ceil 会超），
同时把**行宽也按上限收窄**（比上限还宽的一行永远塞不进一个组）。

### F21 — MV 汇集主干可能从块身上穿过去 ❌

主干原来取"行的中心"。**每行块数是奇数时中心正好落在中间那块块上**。
修复：主干走**第一条分隔带**，与每行几块无关。

### F22 — 报告 §9 写了两处与图不符的数字 ❌

1. `blocks_per_group` 回显的是**请求的上限**（没传就是规则档默认值 8），
   而搜索排出的组有 40 块 → 报告写 **"1 group(s) × ≤ 8 blocks"，图上是 40 块**。
   修复：这个字段改为**实际排出的最大组**，是结果不是请求。
2. 代表性组的图固定画 `default_blocks_per_group = 8` 块，
   而同一节的表格说组有 10 块 → **同一节自相矛盾**。
   修复：代表性组按**站级实际排出的组大小和行宽**画，是整站的一个切片。

### 顺带清理

- `unit_offsets_m()` 在循环里重复调用 `end_gap_sequence()`（O(n²)）；
- `render_site_svg` 每行重复构造一次块偏移表；
- `SiteArrayLayout.blocks_per_row` 的注释还写着 "(<= 2)"；
- 标题里的 `6.06 M STATION` 改成 **`20 FT STATION` / `40 FT STATION`**
  —— 报原始米数对读图的人没有意义；
- 我引入的两个未使用导入（`Optional` / `compute_layout`）。

### 项目规程本身的一条遗漏

`CLAUDE.md` → `CURRENT_STATUS §4.2` 规定：**域的职责变化必须在同一个 commit 里
更新模块地图**。我连续三个 commit 新增/改变了排布与站级两个域的职责，
**都没更新**。本次已补：模块地图新增
「Typical AC Block Arrangement（契约）」「Arrangement geometry」「Site array (L2)」
三行，并新增工作规则 2b「一个规则只能有一个家」。

### 回归锁

`tests/unit/test_typical_ac_block_arrangement.py`（+5）与
`tests/unit/test_site_array_concept.py`（+3）把 F17–F22 全部锁住，
包括对**上限矩阵**（N × cap）和**主干位置**的断言。590 passed。

## 二之三、视角统一 + 网页引擎同步（owner 2026-08-03）

> "网页上 TYPICAL AC BLOCK arrangement 时的排布引擎也要同步调整，当前版本似乎还是
> 之前的引擎！请同步一下，另外摆放方式最好还是 原来那套引擎的视角，要统一一下！"

### F4 — 网页与报告用的是两套引擎 ❌

| | 引擎 | 尺寸来源 |
|---|---|---|
| 报告 §8 | `ac_block_arrangement_v2` / `ac_block_bilateral_layout` | 规则档 + AC Block 型号 |
| 网页 | `layout_block_renderer`（旧栅格） | 页面上的 `2x2 / 1x4 / 4x1` 预设 + 手填净距 |

同一个 AC Block 在网页和报告里能画出**两种不同的排布和尺寸**，且网页那套的净距
没有规范出处，也不区分 20 ft / 40 ft 站体。

**修复**：新增 `calb_sizing_tool/plugins/layout_arrangement_v2_plugin.py`
（`layout_arrangement_v2`），走**报告那套规则引擎**，并**注册为第一个 / 默认渲染器**；
`layout_service.render_layout_from_run_bundle` 的默认 `plugin_id` 也改为它。
旧栅格渲染器保留在下拉框里但不再是默认。选中规则引擎时，页面把
`2x2 / 1x4 / 4x1` 与手填净距控件隐藏——因为这套引擎的尺寸全部由规则档和 AC Block
型号解析，留着只会暗示"可以调得和报告不一样"。

### F5 — 两套引擎各画各的设备图元 ❌

DC 集装箱和 PCS&MV 站体的画法在两个模块里各写一份，导致同一个产品在两张图里
"长得不一样"。**修复**：图元统一收敛到
`ac_block_arrangement_v2.draw_dc_container()` / `draw_mv_station()`，
双侧引擎 import 使用；调色板与标注样式也一并共用。现在两张图是同一视角、同一套
图例：北向上、设备基座、无门面的屋顶泄爆口排、站体百叶仓位、跨通道电缆沟、
底部包络标注。

> 顺带修掉两处：站体标签用 20 ft 常量定位（40 ft 站体的标题偏 3 m）；
> SVG 里混入中文（报告 cairosvg 的等宽字体无 CJK 覆盖，会渲染成豆腐块）。

## 二之四、§9 站阵列与 §8 必须描述同一个 AC Block

### F6 — §9 用 20 ft 站体铺 10 MW 的块 ❌

`compute_site_array()` 调 `compute_layout(dc_per_block, profile)` 时
**既不传 PCS 数也不传功率**，于是 10 MW / 8-PCS 的块在 §9 里按 20 ft 铺排，
每行少算 6.13 m，与 §8 的图自相矛盾（F1 在站级又犯了一遍）。

**修复**：`compute_site_array(..., pcs_per_block=...)`，包络取自
`compute_layout(dc, profile, pcs_count=..., block_power_mw=...)`；
`SiteArrayLayout` 新增 `station_length_m` / `end_gap_m`，站级图元照此绘制。

### F7 — 中央站体的块无法用 L2 行模型铺排

L2 行模型的前提是**站体在行端、朝共用 MV 走廊**；一字型双侧块的站体在**中央**，
不满足该前提。原代码只对 `layout_variant == BILATERAL` 抑制 §9，通用 8PCS/8DC
运行则照旧铺排——正是"同一个块两个尺寸"。

**修复（第一轮）**：抑制条件改成与 §8 完全相同的**形态判定**
（`_uses_central_station_block`），并且不再静默省掉 §9，改为输出一节文字说明。

> **已被 F13 取代。** 出文字等于没做"整张"。第二轮给 `BlockForm` 加了真实
> placements，中央站体的块可以真正铺排，§9 现在**画的就是 §8 那个块**。
> 这条留在这里是为了记录过程，不要照它去恢复"抑制 + 文字"的做法。

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

### P1-3 修 F3：按实际形态选择排布引擎，而非只看 `layout_variant` ✅
1. `report_v2` 的 `is_bilateral` 判定改为：
   `layout_variant == BILATERAL` **或**（`pcs_per_block == 8` 且 `dc_per_ac == 8`）。
2. 通用运行落到 8PCS/8DC 时，走**与受管运行完全相同**的一字型双侧引擎
   （图注仍标 Concept / 假定）。**不再按运行类型分叉画法。**
3. 若两者都不满足，才回退线性引擎。

### P1-4 防回归 ✅
- 数值断言测试：
  - `test_ten_mw_block_is_drawn_with_the_forty_foot_station_not_the_twenty`
    —— 10 MW / 8-PCS 的块，§8 图注必须是 40 ft 站体的包络，不能是 20 ft 的；
  - `test_site_array_power_and_energy_match_the_ac_sizing_tables`
    —— §9 图注功率/能量 == §6 表格值（跨章一致性）；
  - `test_station_length_follows_the_ac_block_class_not_a_constant` /
    `test_site_block_width_equals_the_arrangement_engine_envelope`
    —— §9 铺排的块宽必须等于 §8 引擎算出的包络；
  - `test_eight_by_eight_report_states_site_composition_instead_of_wrong_geometry`
    —— 8/8 时 §9 出文字说明，不出第二个尺寸，也不静默消失。
- "**站体尺寸/每块功率/每 DC 能量一律不得硬编码**"已写入
  `ac_block_arrangement_v2` 与 `site_array_concept` 的**模块级 docstring**。

### P1-5 网页引擎同步 + 视角统一（F4 / F5）✅
1. 新增 `layout_arrangement_v2` 插件（报告同款引擎），注册为默认渲染器；
   `layout_service` 默认 `plugin_id` 同步改为它。
2. 页面在选中规则引擎时隐藏 `2x2 / 1x4 / 4x1` 与手填净距控件。
3. 设备图元收敛到 `draw_dc_container()` / `draw_mv_station()`，两套引擎共用；
   调色板、标注样式、视角一并统一。
4. 回归锁：`tests/unit/test_layout_arrangement_v2_plugin.py`。

### 执行顺序建议（全部已完成）
`P0-2`（报告自相矛盾，客户可见，改动最小且零风险）✅
→ `P0-1`（尺寸修正，需同步基线）✅
→ `P1-3`（引擎选择，影响图形形态，需 owner 看图确认）✅
→ `P1-5`（网页引擎同步 + 视角统一）✅
→ `P1-4`（回归锁定）✅

### P1-6 占地面积最小化（F8 / F9 / F10）✅
1. `end_gap_sequence()`：端面间隙交替 0.9 / 3.0，设备端朝块边界。
2. `_max_rows_per_group()`：按消防可达距离把组填满，少修消防道。
3. `land_area_m2` / `land_per_block_m2` / `land_per_mwh_m2` 报出占地。
4. 回归锁：`test_end_gaps_alternate_so_the_cheap_gaps_land_inside_the_block`、
   `test_alternating_ends_are_strictly_shorter_than_a_flat_equipment_gap`、
   `test_groups_are_filled_to_the_fire_access_limit_not_a_fixed_row_count`、
   `test_land_falls_when_the_plain_ends_face_inward`。

### P1-7 整站占地最小化（F11 / F12 / F13 / F14）✅
1. 环形消防道，内部道路接入；`perimeter_clear_m` 不再叠加。
2. `plan_site_packing()` 搜索每行块数，按占地最小选，受消防可达距离约束。
3. `BlockForm`（含真实 placements + `mirrorable`）让任意块形都能铺排；
   8PCS/8DC 的 §9 从"没有"变成"画的就是 §8 那个块"。
4. 占地数字标明不含升压站/运维楼/堆场/雨水/退界。
5. 回归锁：`test_fire_roads_form_a_connected_loop_not_disconnected_stubs`、
   `test_blocks_per_row_is_searched_for_minimum_land`、
   `test_the_search_beats_a_fixed_two_per_row_on_large_sites`、
   `test_a_central_station_block_is_tiled_from_its_real_placements`、
   `test_the_reported_land_states_what_it_excludes`。

### P1-8 报告与页面一致性收口（F15 / F16）✅
1. `calb_diagrams/typical_ac_block_arrangement.py` —— 引擎选择、标题、取数、
   水印的**唯一实现**；报告 §8 与页面插件都只调 `render_typical_ac_block()`。
2. `report_v2._uses_central_station_block()` 委托同一条规则，§8/§9/页面同源。
3. 页面只提供规则引擎（`ARRANGEMENT_PLUGIN_ID` 单点定义），旧栅格引擎不再暴露。
4. 回归锁：`tests/unit/test_typical_ac_block_arrangement.py`
   —— 剥水印后**逐字节相等** + `inspect.getsource` 防止规则被重新实现。

### 尚未做（明确记录，等 owner 决定）
- **L3 / P2 真实场地几何**：§9 现在画的是**规整网格 + 环道**的概念铺排，
  仍然没有对着真实地块边界、进场道路、地形和退界排布。这一步还需要 owner 提供
  地块红线与接入点。**上面那张"每块占地"表可以直接当 L3 的校核目标值。**
- **规则档本身**：设备 147.9 m²/块，整站 502 m²/块（13 块站），设备占比 29%。
  块级已经压到 349 m²/块（设备占比 42.4%），剩下的 153 m²/块全在**环形消防道
  和组间道路**——规范强制。纯 DC 场理论下限 32.7 m²/台，现方案块级 43.6 m²/台。
  **再往下压只能靠松动规则档（例如以 UL 9540A 试验支撑更小净距），
  排布本身已经到底了。**
- **占地口径**：现数字是环道以内的设备 + 通道。真实征地还要加升压站、运维楼、
  堆场、雨水设施和退界，通常是这个数的数倍。报告里已写明，不要直接当征地面积用。

---

## 四、影响面

| 模块 | 改动 |
|---|---|
| `calb_diagrams/ac_block_arrangement_v2.py` | 站体尺寸参数化（F1）；共用设备图元 `draw_dc_container` / `draw_mv_station`（F5） |
| `calb_diagrams/ac_block_bilateral_layout.py` | 删除四面环绕；渲染改用共用图元与共用调色板（F5） |
| `calb_diagrams/site_array_concept.py` | 删硬编码、改签名（F2）；按 AC Block 型号解析站体（F6） |
| `calb_sizing_tool/reporting/report_v2.py` | 传真实功率/能量；§8/§9 都走共享排布入口（F3/F15）；§9 用真实 placements 铺排中央站体块（F7→F13） |
| `calb_diagrams/typical_ac_block_arrangement.py` | **新增** —— 排布的唯一入口：引擎选择 / 标题 / 取数 / 水印（F15） |
| `calb_sizing_tool/plugins/layout_arrangement_v2_plugin.py` | **新增** —— 网页走报告同款规则引擎（F4）；现已收敛为薄壳，只解析形状（F15） |
| `calb_sizing_tool/plugins/registry.py`、`services/layout_service.py` | 规则引擎注册为默认渲染器（F4） |
| `calb_sizing_tool/ui/site_layout_view.py` | 规则引擎下隐藏无效的栅格/净距控件（F4）；只提供一个渲染器（F16） |
| `calb_sizing_tool/services/layout_service.py` | `ARRANGEMENT_PLUGIN_ID` 单点定义（F16） |
| `tests/` + SLD/报告基线 | 新增断言、重生成基线 |

**不涉及**：DC/AC sizing 计算本身（`ac_sizing_service.py` 等冻结模块不动），
电气拓扑与 SLD 单线图逻辑不动。

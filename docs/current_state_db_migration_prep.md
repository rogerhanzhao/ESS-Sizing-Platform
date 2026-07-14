# CALB Sizing Tool Current State and DB Migration Prep

## 1. 这套系统现在是什么

这是一个以 `Streamlit` 为入口的单体 BESS/ESS 选型工具，当前主流程是：

1. `DC Sizing`
2. `AC Sizing`
3. `Single Line Diagram`
4. `Site Layout`
5. `Report Export`

当前版本没有数据库，核心业务数据主要依赖两类存储：

- 运行态内存：`st.session_state`
- 文件态资源：`data/*.xlsx`、`outputs/*.svg|png`、`user_preferences.json`

这意味着它是“页面驱动 + 会话驱动 + 文件补充”的实现，不是“项目驱动 + 持久化驱动”的实现。

## 2. 代码结构总览

### 2.1 入口

- `app.py`
  - 负责页面导航。
  - 没有后端 API 层，没有服务层容器，没有数据库连接层。

### 2.2 主要模块

- `calb_sizing_tool/ui`
  - 页面层。
  - 但当前也承载了大量业务计算和数据封装逻辑。
- `calb_sizing_tool/state`
  - 会话状态管理。
  - 目前存在 3 套并行状态模型：`app_state`、`session_state/shared_state`、`project_state`。
- `calb_sizing_tool/reporting`
  - DOCX 报告上下文组装、格式化、导出。
- `calb_sizing_tool/sld`
  - SLD 快照、单元组装、校验。
- `calb_diagrams`
  - SLD/Layout 的 `spec` 和 SVG 渲染器。
- `data`
  - Excel 数据字典，是当前系统的“主数据来源”。

### 2.3 实际业务逻辑分布

需要特别注意：`calb_sizing_tool/sizing/dc_logic.py` 和 `calb_sizing_tool/sizing/ac_logic.py` 目前只是轻量占位实现，真正可运行的核心逻辑主要在页面文件里：

- `calb_sizing_tool/ui/dc_view.py`
- `calb_sizing_tool/ui/ac_view.py`

这对后续数据库化和服务化很重要，因为当前系统并不是“UI 调服务”，而是“UI 自己做计算 + 写 session”。

## 3. 当前页面流程和数据流

### 3.1 页面流程

| 页面 | 前置依赖 | 核心动作 | 主要输出 |
|---|---|---|---|
| Dashboard | 无 | 展示流程引导 | 无 |
| DC Sizing | Excel 数据字典 | 做 Stage1/Stage2/Stage3 计算 | `dc_result_summary`、`stage13_output`、`dc_results` |
| AC Sizing | 依赖 DC 结果 | 生成 AC:DC 配比、PCS 配置、DC 到 AC/PCS 分配 | `ac_output`、`ac_results` |
| Single Line Diagram | 依赖 DC + AC | 生成单个 AC Block Group 的 SLD | `diagram_results`、`artifacts`、`outputs/sld_latest.*` |
| Site Layout | 依赖 DC + AC | 生成单个 AC Block Group 的布局图 | `layout_results`、`artifacts`、`outputs/layout_latest.*` |
| Report Export | 依赖 DC + AC，可选 SLD/Layout | 组装 V2.1 DOCX 报告 | DOCX 下载字节流 |

### 3.2 当前实际数据主链

当前跨页面真正被反复消费的不是统一领域模型，而是下面几个临时对象：

- `st.session_state["dc_result_summary"]`
  - 给 AC/SLD/Layout 用的轻量 DC 摘要。
- `st.session_state["stage13_output"]`
  - 由 DC 页面打包出来的“跨阶段兼容 DTO”。
  - 给 AC、SLD、Report 使用。
- `st.session_state["ac_output"]`
  - 由 AC 页面生成，给 SLD、Layout、Report 使用。
- `st.session_state["diagram_results"]`
  - 保存 SLD SVG/PNG 和元数据。
- `st.session_state["layout_results"]`
  - 保存 Layout SVG/PNG 和元数据。

可以把现在的系统理解成：

- `DC` 产出一个主中间结果包
- `AC` 在它基础上再产出第二个主中间结果包
- `SLD/Layout/Report` 都从这两个包里各自取字段

## 4. 当前需求清单

下面这份需求清单是按当前代码和测试反推出来的“系统实际上在做什么”，不是历史文档口径。

### 4.1 DC 侧需求

- 支持录入项目名称、POI 功率、POI 容量、项目寿命、保证年、循环次数、POI 电压、频率。
- 支持录入 DC 参数：
  - `DoD`
  - `DC RTE`
  - `RTE Curve Adjustment`
  - `RTE Monotonic`
- 支持录入效率链参数：
  - `DC Cables`
  - `PCS`
  - `MV Transformer`
  - `AC Cables + SW`
  - `HVT`
- 支持 3 种 DC 配置模式：
  - `container_only`
  - `cabinet_only`
  - `hybrid`
- 支持按保证年自动迭代扩容，直到保证年 POI 可用能量满足目标。
- 支持按项目寿命输出逐年退化表和 POI 可用能量柱状图。
- 支持导出 DC 技术报告。

### 4.2 AC 侧需求

- 必须在 DC 运行完成后才能执行。
- 基于 DC Block 总量，生成 3 种 AC:DC 配比选项：
  - `1:1`
  - `1:2`
  - `1:4`
- 支持每个 AC Block 选用固定 PCS 组合或自定义 PCS 组合。
- 支持对总 AC 功率、总能量做基本校验和超配提示。
- 必须输出 DC Block 在各 AC Block、各 PCS feeder 上的分配方案，供 SLD/Layout 使用。

### 4.3 图纸和导出需求

- SLD 页面生成的是“单个 AC Block Group 的单线图”，不是整站全站图。
- Layout 页面生成的是“单个 AC Block Group 的模板化布局图”，不是全站总平。
- Report 页面生成的是 `V2.1` DOCX 报告。
- 报告可以嵌入 SLD 和 Layout 图片，但图片不存在时也允许继续导出。

### 4.4 测试里显式体现的需求

从现有测试看，系统还隐含要求：

- V1 汇总回归结果要稳定。
- DC 报告的段落文本要与旧版本保持兼容。
- SLD 输出中应出现 `DC BUSBAR A/B` 文案。
- SLD 不应再出现旧的 `DC Combiner` 文案。
- Layout 输出中应包含：
  - `Block`
  - `PCS&MVT SKID`
  - `Transformer`
  - `DC Block`

## 5. 主数据来源

### 5.1 Excel 数据字典

当前系统的主数据不是数据库表，而是 `data` 目录下的 Excel：

- DC 数据字典
  - `ess_sizing_data_dictionary_v13_dc_autofit_rte314_fix05_025C94_v2.xlsx`
  - 如果不存在，则回退到 legacy 文件。
- AC 数据字典
  - `AC_Block_Data_Dictionary_v1_1.xlsx`

### 5.2 DC 页面实际使用的 Sheet

`DC Sizing` 主要读取这些 sheet：

- `ess_sizing_case`
- `dc_block_template_314_data`
- `battery_cell_type_314_data`
- `pack_type_314_data`
- `rack_type_314_data`
- `soh_profile_314_data`
- `soh_curve_314_template`
- `rte_profile_314_data`
- `rte_curve_314_template`

### 5.3 主数据现状结论

- Excel 既承担“参数默认值”，也承担“设备模板字典”，还承担“退化/RTE 曲线主数据”。
- 后续数据库改造不能只建业务结果表，还必须把这些字典数据模型化。

## 6. 状态管理现状

### 6.1 现在有 3 套状态模型

#### A. `AppState`

字段包括：

- `user_inputs_dc`
- `user_inputs_ac`
- `sizing_results_dc`
- `sizing_results_ac`
- `sizing_results_final`
- `diagram_inputs`
- `diagram_results`
- `layout_inputs`
- `layout_results`

#### B. `SharedState`

字段包括：

- `dc_inputs`
- `dc_results`
- `ac_inputs`
- `ac_results`
- `diagram_outputs`
- `last_run_timestamps`
- `inputs`
- `results`
- `artifacts`
- `project_name`

#### C. `project_state`

内部又维护：

- `dc_inputs`
- `dc_results`
- `ac_inputs`
- `ac_results`
- `diagram_inputs`
- `diagram_outputs`
- `layout_inputs`
- `layout_outputs`
- `inputs`
- `dc`
- `ac`
- `diagrams`

### 6.2 当前关键 session key

当前真正被页面直接读写的 key 包括：

- `project_name`
- `poi_nominal_voltage_kv`
- `poi_frequency_hz`
- `grid_kv`
- `dc_inputs`
- `dc_results`
- `ac_inputs`
- `ac_results`
- `dc_result_summary`
- `stage13_output`
- `ac_output`
- `diagram_inputs`
- `diagram_results`
- `layout_inputs`
- `layout_results`
- `artifacts`
- `diagram_outputs`
- `layout_svg_bytes`
- `layout_png_bytes`
- `sld_svg_path`
- `sld_png_path`
- `layout_svg_path`
- `layout_png_path`
- `selected_ac_ratio`

### 6.3 状态管理的核心问题

- 同一份业务数据在多个 key 里重复保存。
- 有的 key 保存 dict，有的 key 保存 dataclass，有的 key 保存 DataFrame。
- 页面之间不是依赖统一契约，而是“多 key fallback 读取”。
- `project_state`、`shared_state`、`app_state` 存在职责重叠。
- 很多结果只在当前浏览器会话内存活，页面刷新、会话失效、服务重启都可能丢失。

## 7. DC 计算逻辑

### 7.1 Stage 1：理论 DC 需求计算

Stage 1 的目标是从 POI 目标反推所需 DC 容量和 DC 功率。

核心计算链如下：

```text
eff_chain
  = eff_dc_cables
  * eff_pcs
  * eff_mvt
  * eff_ac_sw
  * eff_hvt

dc_rte_effective
  = clamp(dc_rte_base + rte_adjust)

dc_one_way_eff
  = sqrt(dc_rte_effective)

dc_usable_bol_frac
  = dod * dc_one_way_eff

dc_energy_required
  = poi_mwh / ((1 - sc_loss) * dc_usable_bol_frac * eff_chain)

dc_power_required_mw
  = poi_mw / eff_chain
```

#### 7.1.1 S&C loss 规则

`sc_time_months` 不直接线性计算，而是映射表：

- `1-3 月 -> 2.0%`
- `4 月 -> 2.5%`
- `5 月 -> 2.8%`
- `6 月 -> 3.0%`
- `7 月 -> 3.2%`
- `8 月 -> 3.5%`
- `9 月 -> 3.8%`
- `10 月 -> 4.1%`
- `11 月 -> 4.3%`
- `12 月 -> 4.5%`
- `>12 月 -> 4.5% + 额外月份 * 0.05%`

#### 7.1.2 Stage 1 输出

主要输出字段：

- `eff_dc_to_poi_frac`
- `sc_loss_pct`
- `dc_rte_effective_frac`
- `dc_usable_bol_frac`
- `dc_energy_capacity_required_mwh`
- `dc_power_required_mw`

### 7.2 Stage 2：DC 配置选型

Stage 2 的目标是决定要装多少个 container / cabinet。

#### 7.2.1 模板选择

系统会从 Excel 中挑选：

- 一个 active/default 的 `container` 模板
- 一个 active/default 的 `cabinet` 模板

并且会先根据 cell/pack/rack 数据重新回算 block nameplate，再覆盖 `dc_block_template_314_data` 的容量值。

#### 7.2.2 三种模式

#### `container_only`

```text
container_count = ceil(required_dc_mwh / container_unit_mwh)
```

#### `cabinet_only`

```text
cabinet_count = ceil(required_dc_mwh / cabinet_unit_mwh)
busbars_needed = ceil(cabinet_count / K_MAX)
```

当前 `K_MAX` 固定为 `10`。

#### `hybrid`

逻辑是：

- 先尽量铺满 container
- 对剩余容量用 cabinet 补齐
- 如果 cabinet 数量超过 `K_MAX`，则再加 1 个 container，并取消 cabinet

#### 7.2.3 Stage 2 输出

主要输出字段：

- `mode`
- `dc_nameplate_bol_mwh`
- `oversize_mwh`
- `config_adjustment_frac`
- `block_config_table`
- `container_count`
- `cabinet_count`
- `busbars_needed`

### 7.3 Stage 3：寿命退化和 POI 可交付能量

Stage 3 的目标是按年推演退化和 POI 可用能量。

#### 7.3.1 先选 SOH/RTE profile

#### SOH profile 选择

按下面这个评分选最近 profile：

```text
score = abs(C_Rate - effective_c_rate) * 10
      + abs(Cycles_Per_Year - cycles_per_year) / 365
```

#### RTE profile 选择

只按 `abs(C_Rate - effective_c_rate)` 最近选择。

#### 7.3.2 年度计算逻辑

对于每个 `year = 0..project_life_years`：

1. 从 `soh_curve` 取 `SOH_Relative`
2. 计算绝对 SOH：

```text
SOH_Absolute = SOH_Relative * (1 - sc_loss)
```

3. 从 `rte_curve` 按 `SOH_Band_Min_Pct <= soh_rel` 选一条 RTE
4. 如果启用 `RTE Monotonic`，则对 RTE 曲线做 `cummin()`，确保 SOH 下降时 RTE 不反升
5. 计算：

```text
dc_usable_bol_mwh
  = dc_nameplate_bol_mwh * dod * sqrt(dc_rte_year)

dc_usable_cod_mwh
  = dc_usable_bol_mwh * (1 - sc_loss)

dc_gross_capacity_year
  = dc_nameplate_bol_mwh * (1 - sc_loss) * soh_rel_calc

dc_usable_year
  = dc_usable_cod_mwh * soh_rel_calc

poi_usable_year
  = dc_usable_year * eff_chain

system_rte_year
  = dc_rte_year * eff_chain^2
```

6. 判断是否满足：

```text
poi_usable_year >= poi_energy_req_mwh
```

#### 7.3.3 Stage 3 输出

逐年 DataFrame 主要字段：

- `Year_Index`
- `SOH_Relative`
- `SOH_Absolute`
- `DC_Nameplate_BOL_MWh`
- `DC_Gross_Capacity_MWh`
- `DC_Usable_MWh`
- `DC_RTE_Frac`
- `System_RTE_Frac`
- `POI_Usable_Energy_MWh`
- `Meets_POI_Req`
- `Is_Guarantee_Year`

以及展示字段：

- `SOH_Display_Pct`
- `SOH_Absolute_Pct`
- `DC_RTE_Pct`
- `System_RTE_Pct`

### 7.4 保证年自动迭代扩容

`size_with_guarantee()` 的逻辑不是一次算完，而是：

1. 先按模式求一个初始方案
2. 跑 Stage 3
3. 看保证年 `poi_g` 是否满足目标
4. 不满足就继续加设备

加设备的策略如下：

- `container_only`
  - 每次加 1 个 container
- `cabinet_only`
  - 每次加 1 个 cabinet
- `hybrid`
  - 如果当前 cabinet 小于 `K_MAX` 且已有 cabinet，则 cabinet +1
  - 如果当前 cabinet 为 0，则 cabinet 从 0 变 1
  - 否则 container +1

直到：

- 满足保证年目标
- 或达到 `max_iter`

## 8. DC 页面如何把结果传给后续页面

DC 页面不会把 3 个模式的全部结果都作为统一契约下发，它只会选一个“active mode”继续往后传。

### 8.1 active mode 规则

按当前顺序挑第一个成功的模式：

- 如果启用 `hybrid`，优先 `hybrid`
- 然后 `cabinet_only`
- 最后 `container_only`

### 8.2 对外打包的两个关键对象

#### `dc_result_summary`

轻量摘要，字段包括：

- `mwh`
- `target_mw`
- `voltage`
- `container_count`
- `cabinet_count`
- `total_blocks`
- `mode`
- `dc_block`

#### `stage13_output`

兼容 DTO，字段包括：

- Stage 1 结果
- Stage 2 原始结果 `stage2_raw`
- Stage 3 元数据 `stage3_meta`
- Stage 3 DataFrame `stage3_df`
- `selected_scenario`
- `dc_block_total_qty`
- `container_count`
- `cabinet_count`
- `poi_nominal_voltage_kv`
- `poi_frequency_hz`

这个对象本质上是当前系统最重要的跨页集成载体。

## 9. AC 计算逻辑

### 9.1 输入来源

AC 页面并不是重新读取完整 DC 结果，而是主要依赖：

- `dc_result_summary`
- `stage13_output`

如果缺少这两个对象，AC 页面无法继续。

### 9.2 AC:DC 配比逻辑

当前固定生成 3 个比例：

- `1:1`
- `1:2`
- `1:4`

其含义是“每个 AC Block 承载多少个 DC Block”，而不是 PCS 数量。

#### 9.2.1 AC Block 数量计算

- `1:1 -> ac_blocks = dc_blocks_total`
- `1:2 -> ac_blocks = ceil(dc_blocks_total / 2)`
- `1:4 -> ac_blocks = ceil(dc_blocks_total / 4)`

#### 9.2.2 推荐策略

- `dc_blocks_total <= 4` 时偏向 `1:1`
- 默认始终推荐 `1:2`
- `dc_blocks_total >= 8` 时也标记 `1:4` 为推荐

### 9.3 PCS 配置逻辑

当前推荐组合是固定枚举，不是根据 AC 数据字典动态生成：

- `2 x 1250`
- `2 x 1500`
- `2 x 1725`
- `2 x 2000`
- `2 x 2500`
- `4 x 1250`
- `4 x 1500`
- `4 x 1725`
- `4 x 2000`
- `4 x 2500`

也支持自定义：

- `PCS Count per AC Block`
- `PCS Rating (kW)`

#### 9.3.1 AC 容器尺寸规则

当前规则很直接：

- 单个 AC Block 功率 `> 5MW` -> `40ft`
- 单个 AC Block 功率 `<= 5MW` -> `20ft`（PCS 数量不参与容器尺寸判断）

### 9.4 AC 校验逻辑

#### 9.4.1 能量校验

- 如果 `total_energy < target_mwh * 0.95` -> 报错停止
- 如果 `total_energy > target_mwh * 1.05` -> 只给 warning

#### 9.4.2 功率校验

- 如果 `total_ac_mw < target_mw * 0.95` -> 报错停止
- 如果 `overhead > target_mw * 0.3` -> warning

### 9.5 AC 的关键输出

`ac_output` 主要字段包括：

- `selected_ratio`
- `num_blocks`
- `pcs_per_block`
- `pcs_kw`
- `block_size_mw`
- `total_ac_mw`
- `overhead_mw`
- `dc_blocks_per_ac`
- `dc_allocation_plan`
- `dc_blocks_total`
- `dc_total_mwh`
- `poi_power_mw`
- `poi_energy_mwh`
- `grid_kv`
- `mv_kv`
- `mv_voltage_kv`
- `lv_v`
- `lv_voltage_v`
- `inverter_lv_v`
- `transformer_count`
- `pcs_count_total`

#### 9.5.1 `dc_allocation_plan` 是后续图纸的核心

结构大致是：

```json
[
  {
    "ac_block_index": 1,
    "dc_blocks_total": 4,
    "feeder_allocations": [1, 1, 1, 1]
  }
]
```

SLD 和 Layout 实际上都依赖这个结构。

## 10. SLD 逻辑

### 10.1 SLD 的定位

当前 SLD 不是整站图，而是“一个 AC Block Group”的工程图。

### 10.2 输入来源

SLD 页面主要读取：

- `stage13_output`
- `dc_result_summary`
- `ac_output`
- `diagram_inputs`

### 10.3 自动补默认值

SLD 页面会根据 AC/DC 结果自动补下面这些默认值：

- MV 标签
- RMU 额定参数
- Transformer 参数
- LV busbar 电流
- DC block 电压

用户还可以手动录入：

- RMU
- Transformer
- LV busbar
- cable spec
- DC fuse spec

### 10.4 feeder 分配逻辑

优先用 `ac_output["dc_allocation_plan"]`。

如果拿不到，就降级为全 0 或平均分配。

这说明 AC 页面输出契约对 SLD 至关重要。

### 10.5 生成链路

SLD 生成流程：

1. 从页面输入组装 `sld_inputs`
2. 调 `build_single_unit_snapshot()`
3. 调 `validate_single_unit_snapshot()`
4. 调 `build_sld_group_spec()`
5. 调 `render_sld_pro_svg()`
6. 可选再用 `cairosvg` 转 PNG

#### 10.5.1 重要结论

- `snapshot` 已经生成了，但当前页面没有把它稳定写回 `st.session_state["sld_snapshot"]`
- `Report Export` 却尝试读取 `sld_snapshot`
- 所以报告链路中的 snapshot hash / snapshot id 目前很可能拿不到

这在数据库版本里应当修正。

### 10.6 SLD 输出落点

会写到多个地方：

- `diagram_results`
- `artifacts["sld_svg_bytes"]`
- `artifacts["sld_png_bytes"]`
- `diagram_outputs.sld_svg`
- `diagram_outputs.sld_png`
- `outputs/sld_latest.svg`
- `outputs/sld_latest.png`

注意 `outputs/sld_latest.*` 是全局单文件，会被后续项目覆盖。

## 11. Layout 逻辑

### 11.1 Layout 的定位

Layout 页面生成的是“单个 AC Block Group 的模板布局图”，不是站级总平。

### 11.2 输入来源

主要依赖：

- `stage13_output`
- `dc_result_summary`
- `ac_output`
- `layout_inputs`

### 11.3 DC Block 数量来源

Layout 不自己重新算，而是从 `ac_output["dc_allocation_plan"]` 里提取每个 AC Block 的 `dc_blocks_total`。

### 11.4 自动排列逻辑

当用户选择 `Auto` 时：

- `<=1` -> `1x4`
- `=2` -> `1x4`
- `<=4` -> `2x2`
- `<=8` -> `4x2`
- `>8` -> `4x4`

### 11.5 生成链路

Layout 生成流程：

1. 从页面输入组装 labels、clearance、arrangement
2. 调 `build_layout_block_spec()`
3. 调 `render_layout_block_svg()`
4. 可选转 PNG

### 11.6 输出落点

会写到多个地方：

- `layout_results`
- `artifacts["layout_svg_bytes"]`
- `artifacts["layout_png_bytes"]`
- `diagram_outputs.layout_svg`
- `diagram_outputs.layout_png`
- `outputs/layout_latest.svg`
- `outputs/layout_latest.png`

同样，`layout_latest.*` 也是全局覆盖模式。

## 12. Report 导出逻辑

### 12.1 入口前提

Report 页面要求：

- 已有 DC 结果
- 已有 AC 结果

但 SLD/Layout 图片是可选项。

### 12.2 上下文组装

`build_report_context()` 会尽量从以下来源拼装：

- `stage13_output`
- `stage2_raw`
- `stage3_df`
- `stage3_meta`
- `ac_output`
- `artifacts`
- `diagram_results`
- `layout_results`
- `outputs/sld_latest.*`
- `outputs/layout_latest.*`

如果 `stage3_df` 不在 session 里，它会尝试重新调用 DC 的 `run_stage3()` 计算一次。

#### 12.2.1 这意味着什么

- 报告不是完全消费“已存结果”，而是有“现场补算”的行为。
- 如果 session 中的数据不完整，报告内容可能与页面当时展示的结果出现偏差。

### 12.3 V2.1 报告内容

当前 V2.1 报告包含：

- Cover
- Conventions & Units
- Executive Summary
- Inputs & Assumptions
- Stage 1
- Efficiency Chain
- Stage 2
- Stage 3
- Stage 4
- Integrated Configuration Summary
- Single Line Diagram
- Block Layout
- QC / Warnings

### 12.4 QC 检查

报告里会做一批一致性检查，例如：

- PCS 数量是否匹配
- AC block 数量是否与 ratio 对得上
- 保证年 POI usable 是否低于目标
- power factor 是否越界
- AC template id 与 PCS per block 是否矛盾
- 效率链总值是否等于各组件乘积

这说明 `ReportContext` 已经在承担“数据审计层”的角色。

## 13. 当前最重要的数据丢失和一致性风险

### 13.1 无数据库带来的直接风险

- 页面刷新后，`st.session_state` 可能丢失。
- Streamlit 进程重启后，项目上下文全部丢失。
- 多人同时操作没有项目隔离。
- 不支持历史版本回看。
- 不支持同一项目多次运行比对。

### 13.2 同一数据多处冗余

同一个业务结果当前可能同时存在于：

- `dc_results`
- `project_state["dc_results"]`
- `results["dc"]`
- `stage13_output`
- `dc_result_summary`

AC、SLD、Layout 也有类似重复。

风险是：

- 一个地方更新了，另一个地方没更新
- 页面 fallback 到旧 key，读取到过期值

### 13.3 字段命名不统一

当前同一含义存在多组别名：

- `pcs_kw` / `pcs_power_kw`
- `pcs_count_total` / `total_pcs`
- `lv_v` / `lv_voltage_v` / `inverter_lv_v`
- `grid_kv` / `mv_kv` / `mv_voltage_kv`

这会让数据库落表、接口定义、报表消费都很难稳定。

### 13.4 active scenario 只有一个

DC 页面虽然计算多个模式，但往后只下发一个 active mode。

这意味着：

- 页面上能看到多方案对比
- 但 AC/SLD/Layout/Report 只跟随一个方案

数据库版本应把“多方案结果”和“选中的方案”分开存。

### 13.5 图纸文件是全局 latest 覆盖

`outputs/sld_latest.*` 和 `outputs/layout_latest.*` 是按固定文件名覆盖。

风险：

- A 项目的图会被 B 项目覆盖
- 报告导出时可能读到别的项目的 latest 文件

### 13.6 `sld_snapshot` 没有形成稳定审计链

当前 SLD 生成时已有 snapshot builder，但没有形成稳定持久化链路。

风险：

- 报告无法引用明确的图纸快照 ID
- 后续无法审计“这份报告对应的是哪一版图”

### 13.7 `DataFrame` 和复杂对象不利于持久化

当前跨页对象里包含：

- `pandas.DataFrame`
- `Pydantic model`
- 原始 dict

数据库版本不能直接照搬，需要规范化为：

- 可序列化 JSON
- 明细表
- artifact 文件引用

## 14. 升级为数据库版时建议的领域拆分

### 14.1 先定义“项目”和“运行”

建议至少拆成下面几类实体：

#### 项目主表

- `projects`
  - `project_id`
  - `project_name`
  - `status`
  - `created_at`
  - `updated_at`

#### DC 运行

- `dc_runs`
  - `dc_run_id`
  - `project_id`
  - `inputs_json`
  - `dictionary_version_dc`
  - `active_scenario_id`
  - `created_at`

- `dc_run_scenarios`
  - `scenario_id`
  - `dc_run_id`
  - `mode`
  - `container_count`
  - `cabinet_count`
  - `busbars_needed`
  - `dc_nameplate_bol_mwh`
  - `oversize_mwh`
  - `summary_json`

- `dc_run_scenario_items`
  - `scenario_id`
  - `block_code`
  - `block_name`
  - `form`
  - `unit_capacity_mwh`
  - `count`

- `dc_run_yearly_results`
  - `scenario_id`
  - `year_index`
  - `soh_relative`
  - `soh_absolute`
  - `dc_usable_mwh`
  - `poi_usable_energy_mwh`
  - `dc_rte_frac`
  - `system_rte_frac`
  - `meets_poi_req`

#### AC 运行

- `ac_runs`
  - `ac_run_id`
  - `project_id`
  - `source_dc_run_id`
  - `source_scenario_id`
  - `inputs_json`
  - `selected_ratio`
  - `num_blocks`
  - `pcs_per_block`
  - `pcs_kw`
  - `block_size_mw`
  - `total_ac_mw`
  - `created_at`

- `ac_block_allocations`
  - `ac_run_id`
  - `ac_block_index`
  - `dc_blocks_total`

- `ac_feeder_allocations`
  - `ac_run_id`
  - `ac_block_index`
  - `feeder_index`
  - `dc_block_count`

#### 图纸与报告

- `sld_runs`
  - `sld_run_id`
  - `project_id`
  - `source_dc_run_id`
  - `source_ac_run_id`
  - `group_index`
  - `inputs_json`
  - `snapshot_json`
  - `meta_json`

- `layout_runs`
  - `layout_run_id`
  - `project_id`
  - `source_dc_run_id`
  - `source_ac_run_id`
  - `block_index`
  - `inputs_json`
  - `meta_json`

- `report_runs`
  - `report_run_id`
  - `project_id`
  - `source_dc_run_id`
  - `source_ac_run_id`
  - `source_sld_run_id`
  - `source_layout_run_id`
  - `context_json`
  - `template_version`

- `artifacts`
  - `artifact_id`
  - `owner_type`
  - `owner_id`
  - `artifact_type`
  - `mime_type`
  - `storage_path`
  - `sha256`

### 14.2 再定义“字典数据”

建议把 Excel 里真正影响计算的字典表单独数据库化：

- DC block templates
- rack templates
- pack templates
- cell templates
- SOH profiles
- SOH curves
- RTE profiles
- RTE curves
- AC block templates

并且加上：

- `version`
- `is_active`
- `effective_from`

### 14.3 计算服务要从 UI 页面中剥离

建议把下面几类函数抽成服务层：

- DC Stage 1/2/3 计算服务
- DC guarantee iteration 服务
- AC sizing 服务
- SLD spec builder 服务
- Layout spec builder 服务
- ReportContext builder 服务

页面层只做：

- 输入采集
- 调服务
- 展示结果

### 14.4 统一命名

数据库版需要先统一字段口径，建议固定只保留一组主字段名：

- `mv_voltage_kv`
- `lv_voltage_v`
- `pcs_rating_kw`
- `pcs_count_total`
- `dc_blocks_total`
- `ac_blocks_total`
- `transformer_rating_kva`

避免继续出现多组别名并存。

## 15. 数据库版最小可行改造路径

建议分 4 步做，而不是直接全量重写。

### 第一步

先把 `DC/AC` 计算从 `ui/*.py` 抽离成纯函数服务。

### 第二步

定义统一 DTO：

- `ProjectInput`
- `DCRun`
- `DCScenario`
- `ACRun`
- `SLDRun`
- `LayoutRun`
- `ReportRun`

### 第三步

把当前 `stage13_output`、`dc_result_summary`、`ac_output` 替换成数据库可持久化的标准结果对象。

### 第四步

最后再让 Streamlit 页面从数据库读取/写回，而不是直接互相读 session。

## 16. 当前质量状态

2026-03-12 本地执行 `pytest -q` 的结果：

- `60 passed`
- `5 failed`

### 16.1 失败项含义

- `tests/test_regression_v1_summary.py`
  - 回归摘要中的 `stage3_year0_poi_usable_energy_mwh` 与 golden 不一致。
  - `case01`: `400.997944 -> 402.490689`
  - `case02`: `220.517328 -> 221.326833`
- `tests/test_report.py`
  - DC 报告段落文本新增了 `RTE Curve Adjustment (Δpp)` 行，导致“旧文案不变”测试失败。
- `tests/test_sld_busbar_groups_smoke.py`
  - SLD 输出缺少 `DC BUSBAR A/B` 文案。
- `tests/test_sld_pro_template_smoke.py`
  - SLD 输出缺少 `DC BUSBAR` 文案。

### 16.2 当前结论

- 主流程基本可跑。
- 但报表和图纸链路仍有回归痕迹。
- 在引入数据库前，最好先明确“哪些字段是最终口径、哪些图纸文案是最终要求、哪些结果必须完全回归稳定”。

## 17. 给后续数据库改造的直接结论

如果只看当前代码，后续升级最关键的不是“把 session_state 换成数据库”，而是先完成下面三件事：

1. 定义统一领域模型，替代 `stage13_output` / `dc_result_summary` / `ac_output` 这类临时跨页包。
2. 把页面内计算逻辑抽出成服务层，避免 UI 与业务强耦合。
3. 把图纸、报告、快照都绑定到明确的 `project_id + run_id + scenario_id`。

否则即使接入数据库，也只是把现在的多份冗余状态从内存搬进表里，问题不会真正消失。

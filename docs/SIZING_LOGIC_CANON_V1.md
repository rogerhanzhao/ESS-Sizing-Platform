# Sizing Logic Canon V1

## Owner-approved AC amendment V2 (2026-07-27)

This amendment is the explicit owner approval required to revise the frozen
`ac_sizing_service.py` contract. It does not alter Stage 1/2/3, SOH/RTE,
`K_MAX_FIXED`, POI energy semantics, or the existing power/energy feasibility
thresholds.

- The generic AC grouping set is extended from `1:1 / 1:2 / 1:4` to
  `1:1 / 1:2 / 1:4 / 1:8`, with `ceil(DC / ratio)` and the existing balanced
  allocation rule.
- A user-selected 1:8 grouping exposes an optional `8 x 1250 kW` small-PCS
  candidate. It is not a product lock and catalogue matching is downstream of
  the PCS selection.
- A protected-output capacity validation prevents a PCS count that cannot be
  physically supplied by the smallest balanced DC group. It adds no sizing
  formula or fabricated engineering parameter.

The current authoritative handoff is
`AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md`. The matching SHA-256 is pinned in
`tests/test_frozen_canon_guard.py` as part of this same approval.

## 目标

这份文档把当前项目已经实现并上线使用的 sizing 逻辑固定为 V1 铁律。

适用范围：

- 页面重构
- 服务拆分
- 数据库迁移
- Excel -> DB 主数据迁移
- 新增产品类型
- 新增 SOH / RTE 曲线
- 报告、SLD、Layout 重构

结论先行：

- 当前 DC sizing 的唯一权威在 `calb_sizing_tool/services/stage1_service.py`、`stage2_service.py`、`stage3_service.py`、`dc_pipeline_service.py`
- 当前 AC sizing 的唯一权威在 `calb_sizing_tool/services/ac_sizing_service.py`
- `ui/*.py`、`reporting/*`、`sld/*`、`calb_diagrams/*` 只能消费 sizing 结果，不能私自重算 sizing

## 权威边界

### DC 权威模块

- `stage1_service.py`: Stage 1 输入归一化、效率链、S&C loss、DoD、DC RTE、理论 DC 需求
- `stage2_service.py`: DC block 模板选择、container/cabinet/hybrid 组合
- `stage3_service.py`: SOH/RTE profile 选择、逐年退化、逐年 POI 可用能量
- `dc_pipeline_service.py`: guarantee-year 迭代扩容逻辑

### AC 权威模块

- `ac_sizing_service.py`: AC:DC ratio、PCS 标准库、AC block 数量、功率/能量校验、DC->AC->feeder 分配
- `common/ac_block.py`: AC block 模板字段派生
- `common/allocation.py`: DC block 平衡分配

### 非权威模块

以下模块是适配层，不允许重新定义 sizing 含义：

- `ui/dc_view.py`
- `ui/ac_view.py`
- `reporting/report_context.py`
- `services/sld_input_builder.py`
- `services/sld_topology_builder.py`
- `calb_diagrams/specs.py`

这些模块可以：

- 读取结果
- 校验结果
- 展示结果
- 转换结果

这些模块不可以：

- 私自改公式
- 私自放宽阈值
- 私自更改 block grouping
- 私自新增 fallback 后改变 sizing 结果

## DC 铁律

### 1. Stage 1 输入归一化

- 默认值来自 DC workbook `ess_sizing_case`
- 百分比输入允许 `95` 或 `0.95` 两种写法，统一归一到 fraction
- `sc_time_months` 当前逻辑强制下限为 `3`
- `rte_curve_adjust_pp` 是 percentage point，加法修正，不是乘法修正

### 2. Stage 1 公式顺序不可变

```text
eff_chain
  = eff_dc_cables
  * eff_pcs
  * eff_mvt
  * eff_ac_cables_sw_rmu
  * eff_hvt_others

dc_rte_effective
  = clamp01(dc_round_trip_efficiency + rte_adjust_frac)

dc_one_way_eff
  = sqrt(dc_rte_effective)

dc_usable_bol_frac
  = dod * dc_one_way_eff

dc_energy_capacity_required_mwh
  = poi_energy_req_mwh
    / ((1 - sc_loss_frac) * dc_usable_bol_frac * eff_chain)

dc_power_required_mw
  = poi_power_req_mw / eff_chain
```

### 3. S&C loss 映射不可改写

- `1-3` 月: `2.0%`
- `4` 月: `2.5%`
- `5` 月: `2.8%`
- `6` 月: `3.0%`
- `7` 月: `3.2%`
- `8` 月: `3.5%`
- `9` 月: `3.8%`
- `10` 月: `4.1%`
- `11` 月: `4.3%`
- `12` 月: `4.5%`
- `>12` 月: `4.5% + (months - 12) * 0.05%`

### 4. Stage 2 block 选择规则不可变

- 先按 `Block_Form` 选 `container` / `cabinet`
- 只允许 `Is_Active == 1`
- 优先 `Is_Default_Option == 1`
- 同优先级下按 `Block_Nameplate_Capacity_Mwh` 从大到小选
- block 容量在运行前允许由 `cell -> pack -> rack -> block` 回算覆盖 Excel 原值

### 5. Stage 2 模式规则不可变

#### `container_only`

```text
container_count = ceil(required_dc_mwh / container_unit_mwh)
```

#### `cabinet_only`

```text
cabinet_count = ceil(required_dc_mwh / cabinet_unit_mwh)
busbars_needed = ceil(cabinet_count / K_MAX_FIXED)
```

当前 `K_MAX_FIXED = 10`

#### `hybrid`

规则顺序固定：

1. 先尽量铺满 container
2. 余量用 cabinet 补齐
3. 如果 cabinet 数量超过 `K_MAX_FIXED`，则新增 `1` 个 container，并把 cabinet 清零

### 6. Stage 3 profile 选择规则不可变

#### SOH profile

```text
score
  = abs(C_Rate - effective_c_rate) * 10
  + abs(Cycles_Per_Year - cycles_per_year) / 365
```

取 score 最小值。

#### RTE profile

```text
abs(C_Rate - effective_c_rate)
```

取差值最小值。

### 7. Stage 3 年度计算规则不可变

对 `year_index = 0..project_life_years`：

```text
soh_relative = curve value
soh_absolute = soh_relative * (1 - sc_loss_frac)

dc_rte_frac_year
  = clamp01(raw_rte_from_band + rte_adjust_frac)

dc_usable_bol_mwh
  = dc_nameplate_bol_mwh * dod_frac * sqrt(dc_rte_frac_year)

dc_usable_cod_mwh
  = dc_usable_bol_mwh * (1 - sc_loss_frac)

dc_gross_capacity_mwh
  = dc_nameplate_bol_mwh * (1 - sc_loss_frac) * soh_relative_rounded

dc_usable_mwh
  = dc_usable_cod_mwh * soh_relative_rounded

poi_usable_energy_mwh
  = dc_usable_mwh * eff_chain

system_rte_frac
  = dc_rte_frac_year * eff_chain^2
```

### 8. RTE monotonic 规则不可变

如果 `rte_monotonic_enforce = True`：

- 对同一条 RTE 曲线做 `ffill -> bfill -> cummin`
- 目的是保证 SOH 下行时，RTE 不反向上跳

### 9. Guarantee-year 扩容规则不可变

- guarantee year 先被 clamp 到 `0..project_life_years`
- 初始方案先走一次 Stage 2 + Stage 3
- 若 guarantee year 的 `poi_usable_energy_mwh + 1e-6 < poi_energy_req_mwh`，则继续加设备

当前加设备策略固定为：

- `container_only`: 每轮 `container_count + 1`
- `cabinet_only`: 每轮 `cabinet_count + 1`
- `hybrid`:
  - 如果已有 cabinet 且 `< K_MAX_FIXED`，则 `cabinet_count + 1`
  - 如果 cabinet 当前为 `0`，则先置为 `1`
  - 否则 `container_count + 1`

`max_iter` 当前固定默认 `60`

## AC 铁律

### 1. AC sizing 只能消费已选中的 DC 方案

AC 不重新计算 DC。

AC 只允许消费：

- `dc_result_summary`
- `stage13_output`
- `stage2` 的 block 数量和容量结果

### 2. AC:DC ratio 集合固定

当前只允许三种 ratio：

- `1:1`
- `1:2`
- `1:4`

任何新增 ratio 都属于 V2 逻辑，不得在 V1 中偷偷插入。

### 3. AC block 数量公式固定

```text
1:1 -> ac_blocks_total = dc_blocks_total
1:2 -> ac_blocks_total = ceil(dc_blocks_total / 2)
1:4 -> ac_blocks_total = ceil(dc_blocks_total / 4)
```

### 4. 推荐策略固定

- `1:2` 永远是默认推荐项
- 当 `dc_blocks_total <= 4` 时，`1:1` 额外标记为推荐
- 当 `dc_blocks_total >= 8` 时，`1:4` 额外标记为推荐

### 5. PCS 标准库固定

当前标准 PCS 组合固定为：

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

当前推荐器只在这些离散组合和自定义 PCS 之间切换，不允许偷偷改成动态字典驱动。

### 6. AC block container 规则固定

- 若 `single_block_ac_power > 5 MW`，则 `40ft`
- 若 `pcs_per_block >= 4`，则 `40ft`
- 否则 `20ft`

### 7. AC 可行性阈值固定

#### 能量

- `total_energy < target_energy * 0.95` -> hard error
- `total_energy > target_energy * 1.05` -> warning

#### 功率

- `total_ac_mw < target_power * 0.95` -> hard error
- `total_ac_mw - target_power > target_power * 0.3` -> warning

### 8. DC -> AC -> feeder 分配规则固定

#### AC block 层

使用 `evenly_distribute(dc_blocks_total, ac_blocks_total)`

#### feeder 层

每个 AC block 内使用 `allocate_dc_blocks(dc_blocks_in_group, pcs_per_block)`

当前行为：

- 尽量均匀分配
- 当 `dc_blocks_total >= pcs_count` 时，优先保证每个 PCS 至少 `1` 个 DC block

### 9. `dc_allocation_plan` 是 AC 对下游的权威输出

结构固定为：

```json
[
  {
    "ac_block_index": 1,
    "dc_blocks_total": 4,
    "feeder_allocations": [1, 1, 1, 1]
  }
]
```

`SLD`、`Layout`、`Report` 可以验证这个结构，但不能绕过它重新分配。

### 10. AC 对下游的最小权威字段固定

`ac_output` 至少必须稳定提供：

- `selected_ratio`
- `num_blocks`
- `pcs_per_block`
- `pcs_count_by_block`
- `pcs_kw` / `pcs_rating_kw_each`
- `block_size_mw`
- `total_ac_mw`
- `dc_blocks_total_by_block`
- `dc_blocks_per_feeder_by_block`
- `dc_allocation_plan`
- `transformer_mva`
- `mv_voltage_kv` / `mv_kv` / `grid_kv`
- `lv_voltage_v` / `lv_v` / `inverter_lv_v`
- `pcs_count_total`

## 新产品类型与新曲线的处理原则

### 允许做的事

- 新增 `dc_block_template`
- 新增 `battery_cell / pack / rack` 组合
- 新增 `soh_profile / soh_curve`
- 新增 `rte_profile / rte_curve`
- 新增非破坏性字段
- 新增文档说明

### 不允许偷偷改的事

- 改 Stage 1 公式顺序
- 改 S&C loss 映射
- 改 `K_MAX_FIXED`
- 改 `container_only/cabinet_only/hybrid` 语义
- 改 guarantee loop 的每轮加设备策略
- 改 AC ratio 集合
- 改 PCS 标准库
- 改 AC 校验阈值
- 改 `dc_allocation_plan` 结构

如果确实要改，必须：

1. 先更新这份文档
2. 再更新对应回归测试
3. 再更新 golden cases 或 AC 契约测试
4. 在 PR / 变更说明里明确说明是“逻辑升级”而不是“重构”

## 回归锚点

当前 V1 sizing canon 至少由以下测试共同冻结：

- `tests/integration/test_dc_pipeline_regression.py`
- `tests/unit/test_stage1_service.py`
- `tests/unit/test_stage2_service.py`
- `tests/unit/test_stage3_service.py`
- `tests/unit/test_sizing_logic_contract.py`
- `tests/unit/test_ac_sizing_service.py`
- `tests/unit/test_sld_input_contract.py`
- `tests/unit/test_sld_topology_builder.py`

## 结论

从现在起，当前项目的 sizing 逻辑不是“页面行为”，而是“服务层契约”。

后续所有重构、迁移、重新设计，都必须把：

- DC Stage 1/2/3
- guarantee-year 扩容
- AC ratio / PCS / allocation

视为固定基线。

允许细化，不允许漂移。

# SLD AC Field Contract V1

## Authoritative rule

SLD V1 的正式 AC 输入以 `ac_output` 为来源，但必须先经过：

- `calb_sizing_tool/adapters/ac_to_sld_adapter.py::normalize_ac_output_for_sld`

该 adapter 是唯一允许做 legacy alias 转换的地方。下游 builder、topology、renderer 不允许再自己猜字段。

## Authoritative field map

| AC authoritative field | 含义 | SLD authoritative usage |
| --- | --- | --- |
| `num_blocks` | AC block 总数 | `SldCanonicalInput.ac_blocks_total` |
| `pcs_per_block` | 每个 AC block 的 PCS 数量 | 当前 V1 要求所有 block 一致 |
| `pcs_kw` | 每个 PCS 的额定功率 | 生成 `pcs_rating_kw_list` |
| `block_size_mw` | 单个 AC block 容量 | 必须等于 `pcs_per_block * pcs_kw / 1000` |
| `dc_allocation_plan` | AC block 的正式 DC 分配计划 | 权威来源 |
| `dc_blocks_total_by_block` | 每个 block 的 DC block 总数 | 从 `dc_allocation_plan` 镜像得到 |
| `dc_blocks_per_feeder_by_block` | 每个 block 每个 feeder 的 DC block 分配 | 从 `dc_allocation_plan` 镜像得到 |
| `transformer_mva` | 每个 AC block 的变压器容量 | `SldCanonicalInput.transformer_rating_mva` |
| `transformer_count` | 变压器数量 | 当前 V1 必须等于 `num_blocks` |
| `pcs_count_total` | PCS 总数 | 当前 V1 必须等于 `sum(pcs_count_by_block)` |
| `dc_blocks_total` | 全站 DC block 总数 | 可选镜像字段 |
| `dc_total_mwh` | 全站 DC 总能量 | 可选镜像字段 |
| `mv_voltage_kv` | MV 电压 | 可选镜像字段 |
| `lv_voltage_v` | LV 电压 | 可选镜像字段 |

## Legacy aliases

| Authoritative field | Allowed legacy alias |
| --- | --- |
| `num_blocks` | `ac_blocks_total` |
| `pcs_per_block` | `pcs_count_per_ac_block` |
| `pcs_kw` | `pcs_power_kw`, `pcs_rating_kw_each` |
| `dc_allocation_plan` | `dc_block_allocation` |
| `transformer_mva` | `transformer_rating_mva`, `transformer_kva` |
| `pcs_count_total` | `total_pcs` |
| `mv_voltage_kv` | `mv_kv`, `grid_kv` |
| `lv_voltage_v` | `lv_v`, `inverter_lv_v` |

## Required / optional / compatibility-only

### Required in formal path

- `num_blocks`
- `pcs_per_block`
- `pcs_kw`
- `block_size_mw`
- `dc_allocation_plan`
- `transformer_mva`

### Required outside AC output but still mandatory for formal SLD

- `labels`
- `equipment_ratings`
- `transformer.vector_group`
- `transformer.uk_percent`
- `dc_block_voltage_v`

这些字段来自 `project_settings`；如果没有，再允许 `override_mode` 下的 draft override。

### Optional mirrors

- `transformer_count`
- `pcs_count_total`
- `dc_blocks_total`
- `dc_total_mwh`
- `mv_voltage_kv`
- `lv_voltage_v`

### Compatibility fallback allowed

只允许两类：

1. `ac_to_sld_adapter.py` 内的 legacy alias 转换
2. `override_mode=true` 时的 draft override

## Forbidden fallback

以下 fallback 不再允许出现在正式 SLD builder / topology / renderer 主链：

- 默认 `group_index = 1` 并继续当正式输入使用
- 默认 `pcs_count = 4`
- 默认 `dc_blocks_per_feeder = even distribute`
- 默认 `transformer_mva = block_size_mw / 0.9`
- 默认 RMU / CT / cable / fuse 通用值直接当正式图输入

## Strict mode behavior

`validation_mode = "strict"` 时：

- 缺关键字段直接抛 `SldInputValidationError`
- 不允许 warning 后继续生成正式图

`validation_mode = "draft"` 时：

- 允许显式 override
- 结果必须以 draft 对待，不能替代正式 baseline

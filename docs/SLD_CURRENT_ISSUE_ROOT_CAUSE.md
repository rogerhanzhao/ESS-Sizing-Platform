# SLD Current Issue Root Cause

## 当前为什么会乱

最近这轮重构之前，SLD 的“输入解释权”没有被收口，导致以下三层都在重复解释 AC/DC 结果：

1. `ui/single_line_diagram_view.py`
   页面从 session/project state 直接抓 `ac_output`，再进入 SLD pipeline。
2. `services/sld_input_builder.py`
   builder 一边读当前 AC 输出，一边继续猜 `pcs_power_kw`、`dc_block_allocation`、`total_pcs` 这类旧字段。
3. `calb_diagrams/specs.py` / `calb_diagrams/sld_pro_renderer.py`
   spec builder 和 legacy renderer wrapper 里还保留了旧的拓扑推断与默认工程值。

结果就是：

- 同一个 SLD，不同层会对 `pcs_count`、`dc_blocks_per_feeder`、`transformer_mva` 做重复解释。
- AC 输出字段和 SLD 消费字段不完全同构时，会进入 silent fallback。
- 图虽然能画出来，但核心 feeder / PCS / DC block 关系可能已经不是运行结果，而是兼容逻辑猜出来的。

## 本轮修什么

本轮只修 SLD V1 的结构问题：

1. 收口 authoritative input
   `AcSnapshot -> SldCanonicalInput -> SldTopology` 成为正式主链。
2. 统一 AC -> SLD 字段契约
   只允许 `adapters/ac_to_sld_adapter.py` 做 legacy alias 转换。
3. 收缩 renderer 边界
   renderer 正式入口只吃 `SldTopology`，不再决定 feeder allocation 和 PCS/DC 数量关系。
4. 建立 SLD regression baseline
   对 topology、normalized render output、hash 和关键结构做自动比对。

## 本轮不修什么

以下内容明确不在本轮：

- Layout
- 登录
- RBAC
- DB 主链
- DC/AC sizing 数学逻辑
- Report Export
- UI 样式大改

## 修复后的职责边界

### Authoritative builder

- `calb_sizing_tool/services/sld_authoritative_builder.py`
- `calb_sizing_tool/services/sld_input_builder.py`

职责：

- 从 `DcRunBundle + AcSnapshot + project_settings/override` 构造 `SldCanonicalInput`
- 从 `SldCanonicalInput` 构造 `SldTopology`

### Compatibility adapter

- `calb_sizing_tool/adapters/ac_to_sld_adapter.py`
- `calb_diagrams/specs.py::build_sld_group_spec_from_topology`

职责：

- 单点处理 AC legacy aliases
- 单点把 topology 适配成 renderer 仍在消费的 `SldGroupSpec`

### Deprecated path

- `calb_sizing_tool/sld/snapshot_single_unit.py`
- `calb_sizing_tool/sld/ac_block_group.py`
- `calb_diagrams/sld_pro_renderer.py::_topology_from_legacy_spec`

职责：

- 仅保留历史兼容
- 默认按 `draft` 处理
- 不再代表正式 SLD 生成链

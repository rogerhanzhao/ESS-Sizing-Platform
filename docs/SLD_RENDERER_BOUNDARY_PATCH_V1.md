# SLD Renderer Boundary Patch V1

## 本轮边界收缩到什么程度

本轮不重写整个 renderer，但把正式链路的职责边界压到了下面这条线：

- `SldCanonicalInput`
- `SldTopology`
- `SldGroupSpec` compatibility view
- `render_sld_svg()` geometry renderer

正式路径现在必须以 `SldTopology` 为 renderer 输入。

## 已外移的逻辑

以下逻辑不再允许由正式 renderer 决定：

- feeder count
- feeder allocation
- PCS count
- `dc_blocks_per_feeder`
- group topology 的核心设备关系

这些关系都前移到了：

- `services/sld_input_builder.py`
- `services/sld_authoritative_builder.py`
- `services/sld_topology_builder.py`

## renderer 现在只负责什么

`calb_diagrams/sld_pro_renderer.py::render_sld_svg()` 现在只负责：

- layout profile 选择
- symbol placement
- geometry / line drawing
- summary box 绘制
- SVG / PNG 输出

它不再读取 `ac_output`、`stage13_output`、`session_state` 之类的零散运行时字典来决定拓扑。

## 仍暂时保留在 renderer 的兼容逻辑

以下内容还在 renderer 文件里，但已降级为 compatibility-only：

- `_topology_from_legacy_spec(spec)`
- `render_sld_pro_svg(spec_or_topology, ...)`

这两处保留的原因是历史调用点仍有 `SldGroupSpec` 输入。

### 当前约束

- 这条路径默认按 `draft` 处理
- 只作为 legacy wrapper
- 不能再扩张为正式工程决策入口

## 后续再拆的部分

本轮没有继续拆的内容：

- legacy `SldGroupSpec` 彻底下线
- old snapshot/raw renderer 系列的历史模块清退
- renderer 文件级拆分

这些属于后续阶段，不在 SLD 问题修复 V1 范围内

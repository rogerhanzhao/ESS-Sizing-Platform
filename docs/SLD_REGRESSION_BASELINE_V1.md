# SLD Regression Baseline V1

## 为什么不能只靠截图肉眼判断

SLD “看起来差不多”并不代表结构没变。最近出问题的点，主要是：

- feeder allocation 被重新猜了
- `pcs_count` / `dc_blocks_per_feeder` 和上游结果错位
- draft fallback 混入正式图

这些问题只看截图很难发现。

## 当前 baseline 比较什么

### 1. Topology baseline

文件：

- `tests/fixtures/sld_cases/case01_container_only_group1/topology_baseline.json`

比较内容：

- normalized topology JSON
- `validation_mode`
- `source_trace`
- feeder count
- pcs count
- `dc_blocks_per_feeder`

### 2. Render baseline

文件：

- `tests/fixtures/sld_cases/case01_container_only_group1/render_baseline.json`

比较内容：

- normalized render metadata
- render spec JSON
- SVG key node / geometry counts
- key labels
- selected mode
- renderer input hash
- topology hash
- render spec hash

## 如何生成 baseline

当前基线通过正式 pipeline 生成：

1. 读取 `case_definition.json`
2. 构造 `DcRunBundle + AcSnapshot + project_settings`
3. 调 `prepare_sld_pipeline_from_run_bundle(...)`
4. 对 topology / render output 做 normalize
5. 写回 baseline JSON

## 当前测试入口

- `tests/unit/test_sld_ac_field_contract.py`
- `tests/unit/test_sld_authoritative_builder.py`
- `tests/integration/test_sld_topology_regression.py`
- `tests/integration/test_sld_render_regression.py`

## 更新 baseline 的前提

只有以下场景允许更新 baseline：

- authoritative SLD contract 被明确细化
- topology 设计规则被明确变更
- renderer 几何排布被有意识调整

禁止：

- 因为 silent fallback 或兼容猜测导致 baseline 被动漂移

# Data Model Map V1

## Objective

This document defines the canonical entity and field map for the current DC sizing path. It bridges:

- legacy Excel sheet names
- legacy Streamlit and session field names
- extracted service-layer schemas
- SQLAlchemy persistence entities

The primary acceptance target for V1 is that every field currently used by Stage 1 to Stage 3 code is explicitly defined here with source and meaning.

## Source Inventory

### DC Workbook

Workbook: `data/ess_sizing_data_dictionary_v13_dc_autofit_rte314_fix05_025C94_v2.xlsx`

| Sheet | Role In Current Phase |
| --- | --- |
| `ess_sizing_case` | Default input values for Stage 1 |
| `dc_block_template_314_data` | Container and cabinet block templates for Stage 2 |
| `battery_cell_type_314_data` | Cell master used by nameplate recalculation and future persistence |
| `pack_type_314_data` | Pack master used by nameplate recalculation and future persistence |
| `rack_type_314_data` | Rack master used by nameplate recalculation and future persistence |
| `soh_profile_314_data` | SOH profile lookup for Stage 3 |
| `soh_curve_314_template` | SOH yearly curve lookup for Stage 3 |
| `rte_profile_314_data` | RTE profile lookup for Stage 3 |
| `rte_curve_314_template` | RTE SOH-band curve lookup for Stage 3 |

### AC Workbook

Workbook: `data/AC_Block_Data_Dictionary_v1_1.xlsx`

Current Phase 1 status:

- inventoried only
- not migrated into DB schema in this phase
- reserved for later interface alignment

## Canonical Entity Map

| Canonical Entity | Current Source | Current Runtime Owner | Persistence Target |
| --- | --- | --- | --- |
| `ParameterDefinition` | docs and code catalog | parameter governance | `parameter_definition` |
| `ParameterSet` | future DB and import workflow | parameter governance | `parameter_set` |
| `BatteryCellType` | `battery_cell_type_314_data` | Excel import and nameplate recalc | `battery_cell_type` |
| `PackType` | `pack_type_314_data` | Excel import and nameplate recalc | `pack_type` |
| `RackType` | `rack_type_314_data` | Excel import and nameplate recalc | `rack_type` |
| `DcBlockTemplate` | `dc_block_template_314_data` | Stage 2 block selection | `dc_block_template` |
| `SohProfile` | `soh_profile_314_data` | Stage 3 profile selection | `soh_profile` |
| `SohCurvePoint` | `soh_curve_314_template` | Stage 3 yearly SOH curve | `soh_curve_point` |
| `RteProfile` | `rte_profile_314_data` | Stage 3 profile selection | `rte_profile` |
| `RteCurveBand` | `rte_curve_314_template` | Stage 3 SOH-band RTE lookup | `rte_curve_band` |
| `Project` | UI or API input | case and run ownership | `project` |
| `SizingCase` | UI input and golden case JSON | DC pipeline request contract | `sizing_case` |
| `SizingRun` | service execution | run registry | `sizing_run` |
| `RunInputSnapshot` | service execution | reproducible input capture | `run_input_snapshot` |
| `RunOutputSnapshot` | service execution | reproducible output capture | `run_output_snapshot` |
| `ArtifactRegistry` | report and diagram exports | artifact binding to run | `artifact_registry` |
| `AuditLog` | repository actions | audit trail | `audit_log` |

## Common Lifecycle Fields

These fields apply to persistence entities unless noted otherwise.

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `common.created_at` | Created At | 创建时间 | `-` | datetime | no | persistence_all | system generated timestamp | derived | `created_at` | audit timestamp |
| `common.updated_at` | Updated At | 更新时间 | `-` | datetime | no | persistence_all | system generated timestamp | derived | `updated_at` | audit timestamp |
| `common.version_tag` | Version Tag | 版本标签 | `-` | string | yes | persistence_all | free text, prefer semantic version or import tag | derived | `version_tag` | source version marker |
| `common.source_ref` | Source Reference | 来源引用 | `-` | string | yes | persistence_all | free text path or process name | derived | `source_ref` | import or generation source |
| `common.is_active` | Is Active | 是否有效 | `-` | boolean | no | master_data,case,artifact | boolean | source or system | `Is_Active` or `is_active` | soft-active flag |
| `common.is_published` | Is Published | 是否发布 | `-` | boolean | no | parameter,master_data,case,artifact | boolean | system | `is_published` | publish-state flag |

## ParameterDefinition And ParameterSet

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `parameter_definition.field_code` | Field Code | 字段编码 | `-` | string | no | parameter_governance | unique | derived | `field_code` | canonical registry key |
| `parameter_definition.display_name_en` | English Name | 英文名称 | `-` | string | no | parameter_governance | non-empty | derived | `display_name_en` | UI and docs label |
| `parameter_definition.display_name_zh` | Chinese Name | 中文名称 | `-` | string | no | parameter_governance | non-empty | derived | `display_name_zh` | UI and docs label |
| `parameter_definition.unit` | Unit | 单位 | `-` | string | no | parameter_governance | one of domain units | derived | `unit` | canonical unit token |
| `parameter_definition.data_type` | Data Type | 数据类型 | `-` | string | no | parameter_governance | string, integer, float, boolean, percent, json | derived | `data_type` | validation dispatch |
| `parameter_definition.nullable` | Nullable | 可空 | `-` | boolean | no | parameter_governance | boolean | derived | `nullable` | contract flag |
| `parameter_definition.required_for_stage` | Required Stage | 适用阶段 | `-` | string | no | parameter_governance | stage or scope code | derived | `required_for_stage` | stage applicability |
| `parameter_definition.validation_rule` | Validation Rule | 校验规则 | `-` | string | no | parameter_governance | rule text required | derived | `validation_rule` | human-readable validation |
| `parameter_definition.source_sheet` | Source Sheet | 来源工作表 | `-` | string | no | parameter_governance | workbook sheet or `derived` | derived | `source_sheet` | trace to legacy source |
| `parameter_definition.legacy_field_name` | Legacy Field Name | 旧字段名 | `-` | string | no | parameter_governance | non-empty | derived | `legacy_field_name` | old code or Excel label |
| `parameter_set.set_code` | Parameter Set Code | 参数集编码 | `-` | string | no | parameter_governance | unique | derived | `set_code` | versionable parameter bundle |
| `parameter_set.parameter_values_json` | Parameter Values | 参数值集合 | `-` | json | no | parameter_governance | valid JSON object | derived | `parameter_values_json` | materialized parameter set |

## SizingCase Input Contract

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sizing_case.fixture_id` | Fixture Id | 基线样例编号 | `-` | string | yes | baseline_only | optional | JSON fixture | `fixture_id` | used by regression only |
| `sizing_case.project_name` | Project Name | 项目名称 | `-` | string | no | stage1 | non-empty | `ess_sizing_case` or UI | `project_name` | request identity |
| `sizing_case.scenario_id` | Scenario Mode | 方案模式 | `-` | string | no | stage2 | enum `container_only,cabinet_only,hybrid` | UI | `scenario_id` | Stage 2 branch selector |
| `sizing_case.poi_power_req_mw` | POI Power Requirement | POI 功率需求 | `MW` | float | no | stage1 | > 0 | `ess_sizing_case` or UI | `poi_power_req_mw` | target POI MW |
| `sizing_case.poi_energy_req_mwh` | POI Energy Requirement | POI 电量需求 | `MWh` | float | no | stage1 | > 0 | `ess_sizing_case` or UI | `poi_energy_req_mwh` | target POI usable energy |
| `sizing_case.poi_nominal_voltage_kv` | POI Nominal Voltage | POI 额定电压 | `kV` | float | yes | future_ac | > 0 when used | UI | `poi_nominal_voltage_kv` | not used by DC math in V1 |
| `sizing_case.poi_frequency_hz` | POI Frequency | POI 频率 | `Hz` | float | yes | future_ac | 50 or 60 when used | UI | `poi_frequency_hz` | not used by DC math in V1 |
| `sizing_case.project_life_years` | Project Life | 项目寿命 | `year` | integer | no | stage1,stage3 | >= 0 | `ess_sizing_case` or UI | `project_life_years` | Stage 3 loop length |
| `sizing_case.cycles_per_year` | Cycles Per Year | 年循环次数 | `cycles/year` | integer | no | stage1,stage3 | >= 0 | `ess_sizing_case` or UI | `cycles_per_year` | SOH profile selection |
| `sizing_case.poi_guarantee_year` | Guarantee Year | 质保年限点 | `year` | integer | no | stage1,stage3 | 0 <= year <= project life | `ess_sizing_case` or UI | `poi_guarantee_year` | guarantee-year pass or fail |
| `sizing_case.eff_dc_cables` | DC Cable Efficiency | DC 电缆效率 | `%` | percent | yes | stage1 | 0 to 100 or 0 to 1 normalized | `ess_sizing_case` or UI | `eff_dc_cables` | input efficiency factor |
| `sizing_case.eff_pcs` | PCS Efficiency | PCS 效率 | `%` | percent | yes | stage1 | 0 to 100 or 0 to 1 normalized | `ess_sizing_case` or UI | `eff_pcs` | input efficiency factor |
| `sizing_case.eff_mvt` | MVT Efficiency | 变压器效率 | `%` | percent | yes | stage1 | 0 to 100 or 0 to 1 normalized | `ess_sizing_case` or UI | `eff_mvt` | input efficiency factor |
| `sizing_case.eff_ac_cables_sw_rmu` | AC Cable SW RMU Efficiency | AC 电缆与开关效率 | `%` | percent | yes | stage1 | 0 to 100 or 0 to 1 normalized | `ess_sizing_case` or UI | `eff_ac_cables_sw_rmu` | input efficiency factor |
| `sizing_case.eff_hvt_others` | HVT Other Efficiency | 高压侧其他效率 | `%` | percent | yes | stage1 | 0 to 100 or 0 to 1 normalized | `ess_sizing_case` or UI | `eff_hvt_others` | input efficiency factor |
| `sizing_case.sc_time_months` | Storage Charge Time | 静置月数 | `month` | integer | yes | stage1 | >= 0, normalized to minimum 3 in current logic | `ess_sizing_case` or UI | `sc_time_months` | maps to S&C loss |
| `sizing_case.dod_pct` | Depth Of Discharge | 放电深度 | `%` | percent | yes | stage1 | 0 to 100 or 0 to 1 normalized | `ess_sizing_case` or UI | `dod_pct` | usable-energy factor |
| `sizing_case.dc_round_trip_efficiency_pct` | DC Round Trip Efficiency | DC 往返效率 | `%` | percent | yes | stage1 | 0 to 100 or 0 to 1 normalized | `ess_sizing_case` or UI | `dc_round_trip_efficiency_pct` | base DC RTE input |
| `sizing_case.rte_curve_adjust_pp` | RTE Curve Adjust | RTE 曲线修正 | `%` | float | yes | stage1,stage3 | percentage points, can be negative | `ess_sizing_case` or UI | `rte_curve_adjust_pp` | additive pp adjustment |
| `sizing_case.rte_monotonic_enforce` | Enforce RTE Monotonicity | 强制 RTE 单调 | `-` | boolean | yes | stage1,stage3 | boolean | UI | `rte_monotonic_enforce` | Stage 3 curve cleanup flag |

## Stage 1 Computed Contract

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `stage1.eff_dc_cables_frac` | DC Cable Efficiency Fraction | DC 电缆效率系数 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `eff_dc_cables_frac` | normalized input |
| `stage1.eff_pcs_frac` | PCS Efficiency Fraction | PCS 效率系数 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `eff_pcs_frac` | normalized input |
| `stage1.eff_mvt_frac` | MVT Efficiency Fraction | 变压器效率系数 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `eff_mvt_frac` | normalized input |
| `stage1.eff_ac_cables_sw_rmu_frac` | AC Efficiency Fraction | AC 侧效率系数 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `eff_ac_cables_sw_rmu_frac` | normalized input |
| `stage1.eff_hvt_others_frac` | HVT Other Efficiency Fraction | 高压侧其他效率系数 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `eff_hvt_others_frac` | normalized input |
| `stage1.eff_dc_to_poi_frac` | End To End Efficiency | DC 到 POI 总效率 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `eff_dc_to_poi_frac` | frozen regression output |
| `stage1.sc_loss_pct` | Storage Charge Loss | 静置损耗 | `%` | float | no | stage1_output | >= 0 | derived | `sc_loss_pct` | from `calc_sc_loss_pct` |
| `stage1.sc_loss_frac` | Storage Charge Loss Fraction | 静置损耗系数 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `sc_loss_frac` | `sc_loss_pct / 100` |
| `stage1.dod_frac` | DOD Fraction | 放电深度系数 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `dod_frac` | normalized input |
| `stage1.dc_round_trip_efficiency_frac` | Effective DC RTE | 生效 DC 往返效率 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `dc_round_trip_efficiency_frac` | effective RTE used in Stage 1 |
| `stage1.dc_rte_base_frac` | Base DC RTE | 基础 DC 往返效率 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `dc_rte_base_frac` | normalized from input |
| `stage1.dc_rte_effective_frac` | Adjusted DC RTE | 修正后 DC 往返效率 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `dc_rte_effective_frac` | after pp adjustment and clamp |
| `stage1.rte_adjust_frac` | RTE Adjust Fraction | RTE 修正系数 | `fraction` | float | no | stage1_output | can be negative | derived | `rte_adjust_frac` | pp converted to fraction |
| `stage1.dc_one_way_efficiency_frac` | DC One Way Efficiency | DC 单程效率 | `fraction` | float | no | stage1_output | 0 to 1 | derived | `dc_one_way_efficiency_frac` | `sqrt(dc_rte_effective_frac)` |
| `stage1.dc_usable_bol_frac` | DC Usable BOL Fraction | BOL 可用系数 | `fraction` | float | no | stage1_output | >= 0 | derived | `dc_usable_bol_frac` | `dod * one_way_eff` |
| `stage1.dc_energy_capacity_required_mwh` | Required DC Energy Capacity | 所需 DC 容量 | `MWh` | float | no | stage1_output | >= 0 | derived | `dc_energy_capacity_required_mwh` | frozen regression output |
| `stage1.dc_power_required_mw` | Required DC Power | 所需 DC 功率 | `MW` | float | no | stage1_output | >= 0 | derived | `dc_power_required_mw` | frozen regression output |

## BatteryCellType, PackType, RackType

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `battery_cell_type.source_cell_type_id` | Source Cell Type Id | 单体类型源编号 | `-` | integer | yes | import,master_data | unique in source sheet | `battery_cell_type_314_data` | `Cell_Type_Id` | source foreign-key anchor |
| `battery_cell_type.cell_model` | Cell Model | 单体型号 | `-` | string | yes | import,master_data | optional | `battery_cell_type_314_data` | `Cell_Model` | descriptive identity |
| `battery_cell_type.chemistry_code` | Chemistry | 化学体系 | `-` | string | yes | import,master_data | optional | `battery_cell_type_314_data` | `Cell_Chemistry` | chemistry code |
| `battery_cell_type.cell_capacity_ah` | Cell Capacity | 单体容量 | `Ah` | float | yes | import,master_data | > 0 when present | `battery_cell_type_314_data` | `Cell_Capacity_Ah` | used by future analytics |
| `battery_cell_type.cell_nominal_voltage_v` | Cell Nominal Voltage | 单体标称电压 | `V` | float | yes | import,master_data | > 0 when present | `battery_cell_type_314_data` | `Cell_Nominal_Voltage_V` | used by future analytics |
| `battery_cell_type.cell_energy_wh` | Cell Energy | 单体能量 | `Wh` | float | yes | import,master_data | > 0 when present | `battery_cell_type_314_data` | `Cell_Energy_Wh` | used by future analytics |
| `pack_type.source_pack_type_id` | Source Pack Type Id | 包类型源编号 | `-` | integer | yes | import,master_data | unique in source sheet | `pack_type_314_data` | `Pack_Type_Id` | source foreign-key anchor |
| `pack_type.source_cell_type_id` | Source Cell Type Ref | 包到单体源关联 | `-` | integer | yes | import,master_data | must match known cell type when present | `pack_type_314_data` | `Cell_Type_Id` | importer resolves to FK |
| `pack_type.pack_model` | Pack Model | 包型号 | `-` | string | yes | import,master_data | optional | `pack_type_314_data` | `Pack_Model` | descriptive identity |
| `pack_type.cells_in_series` | Cells In Series | 串联单体数 | `count` | integer | yes | import,master_data | >= 0 | `pack_type_314_data` | `Cells_In_Series` | nameplate recalc input |
| `pack_type.cells_in_parallel` | Cells In Parallel | 并联单体数 | `count` | integer | yes | import,master_data | >= 0 | `pack_type_314_data` | `Cells_In_Parallel` | nameplate recalc input |
| `pack_type.pack_nominal_voltage_v` | Pack Nominal Voltage | 包标称电压 | `V` | float | yes | import,master_data | > 0 when present | `pack_type_314_data` | `Pack_Nominal_Voltage_V` | future analytics |
| `pack_type.pack_nameplate_capacity_kwh` | Pack Nameplate Capacity | 包铭牌容量 | `kWh` | float | yes | import,master_data | > 0 when present | `pack_type_314_data` | `Pack_Nameplate_Capacity_Kwh` | nameplate recalc input |
| `rack_type.source_rack_type_id` | Source Rack Type Id | 簇类型源编号 | `-` | integer | yes | import,master_data | unique in source sheet | `rack_type_314_data` | `Rack_Type_Id` | source foreign-key anchor |
| `rack_type.source_pack_type_id` | Source Pack Type Ref | 簇到包源关联 | `-` | integer | yes | import,master_data | must match known pack type when present | `rack_type_314_data` | `Pack_Type_Id` | importer resolves to FK |
| `rack_type.rack_model` | Rack Model | 簇型号 | `-` | string | yes | import,master_data | optional | `rack_type_314_data` | `Rack_Model` | descriptive identity |
| `rack_type.packs_per_rack` | Packs Per Rack | 每簇包数 | `count` | integer | yes | import,master_data | >= 0 | `rack_type_314_data` | `Packs_Per_Rack` | nameplate recalc input |
| `rack_type.rack_nameplate_capacity_mwh` | Rack Nameplate Capacity | 簇铭牌容量 | `MWh` | float | yes | import,master_data | >= 0 | `rack_type_314_data` | `Rack_Nameplate_Capacity_Mwh` | nameplate recalc input |
| `rack_type.rack_aux_energy_kwh` | Rack Aux Energy | 簇辅助能耗 | `kWh` | float | yes | import,master_data | >= 0 | `rack_type_314_data` | `Rack_Aux_Energy_Kwh` | imported reference |

## DcBlockTemplate

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dc_block_template.source_dc_block_template_id` | Source DC Block Template Id | DC 模板源编号 | `-` | integer | yes | stage2_master | unique in source sheet | `dc_block_template_314_data` | `Dc_Block_Template_Id` | source foreign-key anchor |
| `dc_block_template.source_rack_type_id` | Source Rack Type Ref | 模板到簇源关联 | `-` | integer | yes | stage2_master | match known rack type when present | `dc_block_template_314_data` | `Rack_Type_Id` | importer resolves to FK |
| `dc_block_template.dc_block_code` | Block Code | 模块编码 | `-` | string | no | stage2_master | non-empty | `dc_block_template_314_data` | `Dc_Block_Code` | runtime config output field |
| `dc_block_template.dc_block_name` | Block Name | 模块名称 | `-` | string | no | stage2_master | non-empty | `dc_block_template_314_data` | `Dc_Block_Name` | runtime config output field |
| `dc_block_template.block_form` | Block Form | 模块形式 | `-` | string | no | stage2_master | `container` or `cabinet` | `dc_block_template_314_data` | `Block_Form` | Stage 2 selector |
| `dc_block_template.container_length_ft` | Container Length | 箱体长度 | `ft` | integer | yes | stage2_master | >= 0 when present | `dc_block_template_314_data` | `Container_Length_Ft` | reference only |
| `dc_block_template.racks_per_block` | Racks Per Block | 每模块簇数 | `count` | integer | yes | stage2_master | >= 0 | `dc_block_template_314_data` | `Racks_Per_Block` | reference only |
| `dc_block_template.packs_per_block` | Packs Per Block | 每模块包数 | `count` | integer | yes | stage2_master | >= 0 | `dc_block_template_314_data` | `Packs_Per_Block` | reference only |
| `dc_block_template.block_nameplate_capacity_mwh` | Block Nameplate Capacity | 模块铭牌容量 | `MWh` | float | yes | stage2_master | > 0 when active | `dc_block_template_314_data` | `Block_Nameplate_Capacity_Mwh` | Stage 2 capacity basis |
| `dc_block_template.block_aux_energy_kwh` | Block Aux Energy | 模块辅助能耗 | `kWh` | float | yes | stage2_master | >= 0 | `dc_block_template_314_data` | `Block_Aux_Energy_Kwh` | imported reference |
| `dc_block_template.design_max_c_rate` | Design Max C Rate | 设计最大倍率 | `C` | float | yes | stage2_master | >= 0 | `dc_block_template_314_data` | `Design_Max_C_Rate` | reference only |
| `dc_block_template.is_default_option` | Default Option | 默认推荐项 | `-` | boolean | yes | stage2_master | boolean | `dc_block_template_314_data` | `Is_Default_Option` | currently preserved via `raw_row_json` and Excel bundle only |

## SOH Profile And Curve

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `soh_profile.source_profile_id` | SOH Source Profile Id | SOH 源编号 | `-` | integer | yes | stage3_master | unique in source sheet | `soh_profile_314_data` | `Profile_Id` | source anchor |
| `soh_profile.source_cell_type_id` | SOH Source Cell Ref | SOH 到单体源关联 | `-` | integer | yes | stage3_master | match known cell type when present | `soh_profile_314_data` | `Cell_Type_Id` | importer resolves to FK |
| `soh_profile.profile_name` | SOH Profile Name | SOH 曲线名称 | `-` | string | yes | stage3_master | optional | `soh_profile_314_data` | `Profile_Name` | descriptive only |
| `soh_profile.cycles_per_year` | SOH Cycles Per Year | SOH 年循环次数 | `cycles/year` | integer | yes | stage3_master | >= 0 | `soh_profile_314_data` | `Cycles_Per_Year` | profile selection dimension |
| `soh_profile.c_rate` | SOH C Rate | SOH 适用倍率 | `C` | float | yes | stage3_master | >= 0 | `soh_profile_314_data` | `C_Rate` | profile selection dimension |
| `soh_profile.reference_temperature_c` | SOH Reference Temperature | SOH 参考温度 | `C` | float | yes | stage3_master | optional | `soh_profile_314_data` | `Reference_Temperature_C` | imported reference |
| `soh_curve_point.source_profile_id` | SOH Curve Profile Ref | SOH 曲线源关联 | `-` | integer | no | stage3_master | must map to SOH profile | `soh_curve_314_template` | `Profile_Id` | importer resolves to FK |
| `soh_curve_point.life_year_index` | Life Year Index | 寿命年索引 | `year` | integer | no | stage3_master | >= 0 | `soh_curve_314_template` | `Life_Year_Index` | Stage 3 lookup key |
| `soh_curve_point.cycle_index` | Cycle Index | 循环索引 | `count` | integer | yes | stage3_master | >= 0 when present | `soh_curve_314_template` | `Cycle_Index` | imported reference |
| `soh_curve_point.soh_dc_pct` | SOH DC Percent | SOH 百分比 | `%` | percent | no | stage3_master | 0 to 100 or 0 to 1 normalized | `soh_curve_314_template` | `Soh_Dc_Pct` | Stage 3 degradation basis |

## RTE Profile And Curve

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rte_profile.source_profile_id` | RTE Source Profile Id | RTE 源编号 | `-` | integer | yes | stage3_master | unique in source sheet | `rte_profile_314_data` | `Profile_Id` | source anchor |
| `rte_profile.source_cell_type_id` | RTE Source Cell Ref | RTE 到单体源关联 | `-` | integer | yes | stage3_master | match known cell type when present | `rte_profile_314_data` | `Cell_Type_Id` | importer resolves to FK |
| `rte_profile.profile_name` | RTE Profile Name | RTE 曲线名称 | `-` | string | yes | stage3_master | optional | `rte_profile_314_data` | `Profile_Name` | descriptive only |
| `rte_profile.cycles_per_year` | RTE Cycles Per Year | RTE 年循环次数 | `cycles/year` | integer | yes | stage3_master | >= 0 | `rte_profile_314_data` | `Cycles_Per_Year` | imported reference |
| `rte_profile.c_rate` | RTE C Rate | RTE 适用倍率 | `C` | float | yes | stage3_master | >= 0 | `rte_profile_314_data` | `C_Rate` | profile selection dimension |
| `rte_curve_band.source_profile_id` | RTE Curve Profile Ref | RTE 曲线源关联 | `-` | integer | no | stage3_master | must map to RTE profile | `rte_curve_314_template` | `Profile_Id` | importer resolves to FK |
| `rte_curve_band.soh_band_min_pct` | SOH Band Min | SOH 下边界 | `%` | percent | no | stage3_master | 0 to 100 or 0 to 1 normalized | `rte_curve_314_template` | `Soh_Band_Min_Pct` | Stage 3 band lookup key |
| `rte_curve_band.soh_band_max_pct` | SOH Band Max | SOH 上边界 | `%` | percent | yes | stage3_master | optional | `rte_curve_314_template` | `Soh_Band_Max_Pct` | imported reference |
| `rte_curve_band.rte_dc_pct` | DC RTE Percent | DC 往返效率百分比 | `%` | percent | no | stage3_master | 0 to 100 or 0 to 1 normalized | `rte_curve_314_template` | `Rte_Dc_Pct` | Stage 3 efficiency basis |

## Stage 2 And Stage 3 Output Contract

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `stage2.mode` | Stage 2 Mode | 第二阶段模式 | `-` | string | no | stage2_output | enum `container_only,cabinet_only,hybrid` | derived | `mode` | scenario result |
| `stage2.dc_nameplate_bol_mwh` | DC Nameplate BOL | DC 初始铭牌容量 | `MWh` | float | no | stage2_output | >= 0 | derived | `dc_nameplate_bol_mwh` | frozen regression output |
| `stage2.oversize_mwh` | Oversize | 超配容量 | `MWh` | float | no | stage2_output | can be 0 or positive | derived | `oversize_mwh` | Stage 2 summary |
| `stage2.config_adjustment_frac` | Config Adjustment | 配置调整系数 | `fraction` | float | no | stage2_output | >= -1 | derived | `config_adjustment_frac` | Stage 2 summary |
| `stage2.container_count` | Container Count | 集装箱数量 | `count` | integer | no | stage2_output | >= 0 | derived | `container_count` | frozen regression output |
| `stage2.cabinet_count` | Cabinet Count | 柜体数量 | `count` | integer | no | stage2_output | >= 0 | derived | `cabinet_count` | frozen regression output |
| `stage2.busbars_needed` | Busbars Needed | 汇流排数量 | `count` | integer | no | stage2_output | >= 0 | derived | `busbars_needed` | Stage 2 summary |
| `stage2.block_config_items[].block_code` | Block Code | 模块编码 | `-` | string | no | stage2_output | non-empty | derived | `Block Code` | legacy report-compatible column |
| `stage2.block_config_items[].block_name` | Block Name | 模块名称 | `-` | string | no | stage2_output | non-empty | derived | `Block Name` | legacy report-compatible column |
| `stage2.block_config_items[].form` | Form | 形式 | `-` | string | no | stage2_output | `container` or `cabinet` | derived | `Form` | legacy report-compatible column |
| `stage2.block_config_items[].unit_capacity_mwh` | Unit Capacity | 单模块容量 | `MWh` | float | no | stage2_output | > 0 | derived | `Unit Capacity (MWh)` | legacy report-compatible column |
| `stage2.block_config_items[].count` | Count | 数量 | `count` | integer | no | stage2_output | >= 0 | derived | `Count` | legacy report-compatible column |
| `stage2.block_config_items[].subtotal_mwh` | Subtotal | 小计容量 | `MWh` | float | no | stage2_output | >= 0 | derived | `Subtotal (MWh)` | legacy report-compatible column |
| `stage2.block_config_items[].total_dc_nameplate_bol_mwh` | Total DC Nameplate BOL | 总 DC 初始铭牌容量 | `MWh` | float | no | stage2_output | >= 0 | derived | `Total DC Nameplate @BOL (MWh)` | legacy report-compatible column |
| `stage3.meta.effective_c_rate` | Effective C Rate | 有效倍率 | `C` | float | no | stage3_output | >= 0 | derived | `effective_c_rate` | frozen regression output |
| `stage3.meta.soh_profile_id` | Selected SOH Profile | 选中 SOH 曲线编号 | `-` | integer | no | stage3_output | profile id exists | derived | `soh_profile_id` | frozen regression output |
| `stage3.meta.rte_profile_id` | Selected RTE Profile | 选中 RTE 曲线编号 | `-` | integer | no | stage3_output | profile id exists | derived | `rte_profile_id` | frozen regression output |
| `stage3.meta.chosen_soh_c_rate` | Chosen SOH C Rate | 选中 SOH 倍率 | `C` | float | no | stage3_output | >= 0 | derived | `chosen_soh_c_rate` | debug and trace field |
| `stage3.meta.chosen_soh_cycles_per_year` | Chosen SOH Cycles | 选中 SOH 年循环次数 | `cycles/year` | integer | no | stage3_output | >= 0 | derived | `chosen_soh_cycles_per_year` | debug and trace field |
| `stage3.meta.chosen_rte_c_rate` | Chosen RTE C Rate | 选中 RTE 倍率 | `C` | float | no | stage3_output | >= 0 | derived | `chosen_rte_c_rate` | debug and trace field |
| `stage3.year_record.year_index` | Year Index | 年份索引 | `year` | integer | no | stage3_output | >= 0 | derived | `Year_Index` | yearly table primary key |
| `stage3.year_record.soh_relative` | Relative SOH | 相对 SOH | `fraction` | float | no | stage3_output | 0 to 1 | derived | `SOH_Relative` | yearly table |
| `stage3.year_record.soh_absolute` | Absolute SOH | 绝对 SOH | `fraction` | float | no | stage3_output | 0 to 1 | derived | `SOH_Absolute` | yearly table |
| `stage3.year_record.dc_nameplate_bol_mwh` | DC Nameplate BOL | DC 初始铭牌容量 | `MWh` | float | no | stage3_output | >= 0 | derived | `DC_Nameplate_BOL_MWh` | yearly table |
| `stage3.year_record.dc_gross_capacity_mwh` | DC Gross Capacity | DC 毛容量 | `MWh` | float | no | stage3_output | >= 0 | derived | `DC_Gross_Capacity_MWh` | yearly table |
| `stage3.year_record.dc_usable_mwh` | DC Usable Energy | DC 可用电量 | `MWh` | float | no | stage3_output | >= 0 | derived | `DC_Usable_MWh` | yearly table |
| `stage3.year_record.dc_rte_frac` | DC RTE Fraction | DC 效率系数 | `fraction` | float | no | stage3_output | 0 to 1 | derived | `DC_RTE_Frac` | yearly table |
| `stage3.year_record.system_rte_frac` | System RTE Fraction | 系统效率系数 | `fraction` | float | no | stage3_output | 0 to 1 | derived | `System_RTE_Frac` | yearly table |
| `stage3.year_record.poi_usable_energy_mwh` | POI Usable Energy | POI 可用电量 | `MWh` | float | no | stage3_output | >= 0 | derived | `POI_Usable_Energy_MWh` | frozen regression output |
| `stage3.year_record.meets_poi_req` | Meets POI Requirement | 是否满足 POI 需求 | `-` | boolean | no | stage3_output | boolean | derived | `Meets_POI_Req` | yearly pass or fail |
| `stage3.year_record.is_guarantee_year` | Is Guarantee Year | 是否质保年 | `-` | boolean | no | stage3_output | boolean | derived | `Is_Guarantee_Year` | yearly marker |

## Project, Run, Snapshot, Artifact, Audit

| field_code | display_name_en | display_name_zh | unit | data_type | nullable | required_for_stage | validation_rule | source_sheet | legacy_field_name | remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `project.project_code` | Project Code | 项目编码 | `-` | string | no | persistence | unique | derived | `project_code` | stable project key |
| `project.project_name` | Project Name | 项目名称 | `-` | string | no | persistence | non-empty | derived | `project_name` | display name |
| `sizing_case.case_code` | Case Code | 算例编码 | `-` | string | no | persistence | unique | derived | `case_code` | stable case key |
| `sizing_case.stage_scope` | Stage Scope | 阶段范围 | `-` | string | no | persistence | `dc`, future `ac` etc | derived | `stage_scope` | used for routing |
| `sizing_case.scenario_mode` | Scenario Mode | 方案模式 | `-` | string | no | persistence | enum | derived | `scenario_mode` | persisted scenario |
| `sizing_case.input_json` | Case Input JSON | 算例输入快照 | `-` | json | no | persistence | valid JSON object | derived | `input_json` | persisted request |
| `sizing_run.run_type` | Run Type | 运行类型 | `-` | string | no | persistence | `dc_pipeline` in V1 | derived | `run_type` | execution type |
| `sizing_run.status` | Run Status | 运行状态 | `-` | string | no | persistence | `draft,running,succeeded,failed,archived` | derived | `status` | lifecycle status |
| `sizing_run.input_summary_json` | Run Input Summary | 输入摘要 | `-` | json | no | persistence | valid JSON object | derived | `input_summary_json` | quick index payload |
| `sizing_run.output_summary_json` | Run Output Summary | 输出摘要 | `-` | json | no | persistence | valid JSON object | derived | `output_summary_json` | quick index payload |
| `run_input_snapshot.snapshot_kind` | Input Snapshot Kind | 输入快照类型 | `-` | string | no | persistence | non-empty | derived | `snapshot_kind` | for example `case_input` |
| `run_input_snapshot.snapshot_json` | Input Snapshot JSON | 输入快照内容 | `-` | json | no | persistence | valid JSON object | derived | `snapshot_json` | reproducible input |
| `run_output_snapshot.snapshot_kind` | Output Snapshot Kind | 输出快照类型 | `-` | string | no | persistence | non-empty | derived | `snapshot_kind` | for example `stage1_output` |
| `run_output_snapshot.snapshot_json` | Output Snapshot JSON | 输出快照内容 | `-` | json | no | persistence | valid JSON object | derived | `snapshot_json` | reproducible output |
| `artifact_registry.artifact_kind` | Artifact Kind | 制品类型 | `-` | string | no | persistence | `report,sld,layout,snapshot,csv` | derived | `artifact_kind` | run-bound artifact |
| `artifact_registry.file_path` | File Path | 文件路径 | `-` | string | no | persistence | non-empty | derived | `file_path` | filesystem pointer |
| `artifact_registry.content_hash` | Content Hash | 内容哈希 | `-` | string | yes | persistence | optional hash | derived | `content_hash` | reproducibility anchor |
| `audit_log.entity_type` | Entity Type | 实体类型 | `-` | string | no | persistence | non-empty | derived | `entity_type` | audit partition key |
| `audit_log.entity_id` | Entity Id | 实体编号 | `-` | string | no | persistence | non-empty | derived | `entity_id` | audit foreign key surrogate |
| `audit_log.action` | Action | 动作 | `-` | string | no | persistence | non-empty | derived | `action` | audit event |

## Coverage Statement

Stage 1 to Stage 3 code touchpoints are covered as follows:

- [stage1_service.py](d:/CALB_SizingTool/calb_sizing_tool/services/stage1_service.py): `SizingCase Input Contract` and `Stage 1 Computed Contract`
- [stage2_service.py](d:/CALB_SizingTool/calb_sizing_tool/services/stage2_service.py): `DcBlockTemplate` and `Stage 2 And Stage 3 Output Contract`
- [stage3_service.py](d:/CALB_SizingTool/calb_sizing_tool/services/stage3_service.py): `Stage 1 Computed Contract`, `SOH Profile And Curve`, `RTE Profile And Curve`, and `Stage 2 And Stage 3 Output Contract`
- [dc_pipeline_service.py](d:/CALB_SizingTool/calb_sizing_tool/services/dc_pipeline_service.py): `SizingCase Input Contract`, `Stage 1 Computed Contract`, `DcBlockTemplate`, and `Project, Run, Snapshot, Artifact, Audit`

This V1 map is the naming and traceability baseline for all later DB-first migration work.

from __future__ import annotations

from calb_sizing_tool.domain.enums import ParameterDataType, StageCode
from calb_sizing_tool.domain.field_codes import FieldCode
from calb_sizing_tool.domain.units import (
    UNIT_COUNT,
    UNIT_FRACTION,
    UNIT_MONTH,
    UNIT_MW,
    UNIT_MWH,
    UNIT_NONE,
    UNIT_PERCENT,
    UNIT_YEAR,
)
from calb_sizing_tool.schemas.master_data import ParameterDefinitionSchema


def build_parameter_definition_catalog() -> list[ParameterDefinitionSchema]:
    specs = [
        (FieldCode.PROJECT_NAME, "Project Name", "Project Name", UNIT_NONE, ParameterDataType.STRING.value, False, StageCode.STAGE1.value, "non-empty", "ess_sizing_case", "project_name", "Primary case identity."),
        (FieldCode.POI_POWER_REQ_MW, "POI Required Power", "POI Required Power", UNIT_MW, ParameterDataType.FLOAT.value, False, StageCode.STAGE1.value, "> 0", "ess_sizing_case", "poi_power_req_mw", "Target POI export power."),
        (FieldCode.POI_ENERGY_REQ_MWH, "POI Required Energy", "POI Required Energy", UNIT_MWH, ParameterDataType.FLOAT.value, False, StageCode.STAGE1.value, "> 0", "ess_sizing_case", "poi_energy_req_mwh", "Target POI usable energy."),
        (FieldCode.PROJECT_LIFE_YEARS, "Project Life", "Project Life", UNIT_YEAR, ParameterDataType.INTEGER.value, False, StageCode.STAGE1.value, ">= 0", "ess_sizing_case", "project_life_years", "Stage 3 curve horizon."),
        (FieldCode.CYCLES_PER_YEAR, "Cycles Per Year", "Cycles Per Year", "cycles/year", ParameterDataType.INTEGER.value, False, StageCode.STAGE1.value, ">= 0", "ess_sizing_case", "cycles_per_year", "SOH profile selector."),
        (FieldCode.POI_GUARANTEE_YEAR, "POI Guarantee Year", "POI Guarantee Year", UNIT_YEAR, ParameterDataType.INTEGER.value, False, StageCode.STAGE1.value, "0 <= value <= project_life_years", "ess_sizing_case", "poi_guarantee_year", "Guarantee oversize checkpoint."),
        (FieldCode.EFF_DC_CABLES, "DC Cable Efficiency", "DC Cable Efficiency", UNIT_PERCENT, ParameterDataType.PERCENT.value, True, StageCode.STAGE1.value, "0..100 or 0..1 normalized", "ess_sizing_case", "eff_dc_cables", "Stage 1 input."),
        (FieldCode.EFF_PCS, "PCS Efficiency", "PCS Efficiency", UNIT_PERCENT, ParameterDataType.PERCENT.value, True, StageCode.STAGE1.value, "0..100 or 0..1 normalized", "ess_sizing_case", "eff_pcs", "Stage 1 input."),
        (FieldCode.EFF_MVT, "MVT Efficiency", "MVT Efficiency", UNIT_PERCENT, ParameterDataType.PERCENT.value, True, StageCode.STAGE1.value, "0..100 or 0..1 normalized", "ess_sizing_case", "eff_mvt", "Stage 1 input."),
        (FieldCode.EFF_AC_CABLES_SW_RMU, "AC Cable and Switch Efficiency", "AC Cable and Switch Efficiency", UNIT_PERCENT, ParameterDataType.PERCENT.value, True, StageCode.STAGE1.value, "0..100 or 0..1 normalized", "ess_sizing_case", "eff_ac_cables_sw_rmu", "Stage 1 input."),
        (FieldCode.EFF_HVT_OTHERS, "HVT Other Efficiency", "HVT Other Efficiency", UNIT_PERCENT, ParameterDataType.PERCENT.value, True, StageCode.STAGE1.value, "0..100 or 0..1 normalized", "ess_sizing_case", "eff_hvt_others", "Stage 1 input."),
        (FieldCode.SC_TIME_MONTHS, "S&C Time", "S&C Time", UNIT_MONTH, ParameterDataType.INTEGER.value, True, StageCode.STAGE1.value, ">= 0", "ess_sizing_case", "sc_time_months", "Storage and commissioning loss selector."),
        (FieldCode.DOD_PCT, "Depth of Discharge", "Depth of Discharge", UNIT_PERCENT, ParameterDataType.PERCENT.value, True, StageCode.STAGE1.value, "0..100 or 0..1 normalized", "ess_sizing_case", "dod_pct", "Stage 1 usable fraction input."),
        (FieldCode.DC_ROUND_TRIP_EFFICIENCY_PCT, "DC Round Trip Efficiency", "DC Round Trip Efficiency", UNIT_PERCENT, ParameterDataType.PERCENT.value, True, StageCode.STAGE1.value, "0..100 or 0..1 normalized", "ess_sizing_case", "dc_round_trip_efficiency_pct", "Base RTE input."),
        (FieldCode.RTE_CURVE_ADJUST_PP, "RTE Curve Adjustment", "RTE Curve Adjustment", UNIT_PERCENT, ParameterDataType.FLOAT.value, True, StageCode.STAGE1.value, "-5 <= value <= 5", "ess_sizing_case", "rte_curve_adjust_pp", "Percentage-point adjustment."),
        (FieldCode.RTE_MONOTONIC_ENFORCE, "Enforce RTE Monotonicity", "Enforce RTE Monotonicity", UNIT_NONE, ParameterDataType.BOOLEAN.value, True, StageCode.STAGE1.value, "boolean", "derived", "rte_monotonic_enforce", "Stage 3 curve cleanup flag."),
        (FieldCode.EFF_DC_TO_POI_FRAC, "DC to POI Efficiency", "DC to POI Efficiency", UNIT_FRACTION, ParameterDataType.FLOAT.value, False, StageCode.STAGE1.value, "0..1", "derived", "eff_dc_to_poi_frac", "Frozen Stage 1 output."),
        (FieldCode.DC_POWER_REQUIRED_MW, "Required DC Power", "Required DC Power", UNIT_MW, ParameterDataType.FLOAT.value, False, StageCode.STAGE1.value, ">= 0", "derived", "dc_power_required_mw", "Frozen Stage 1 output."),
        (FieldCode.DC_ENERGY_CAPACITY_REQUIRED_MWH, "Required DC Energy Capacity", "Required DC Energy Capacity", UNIT_MWH, ParameterDataType.FLOAT.value, False, StageCode.STAGE1.value, ">= 0", "derived", "dc_energy_capacity_required_mwh", "Frozen Stage 1 output."),
        (FieldCode.DC_NAMEPLATE_BOL_MWH, "DC Nameplate at BOL", "DC Nameplate at BOL", UNIT_MWH, ParameterDataType.FLOAT.value, False, StageCode.STAGE2.value, ">= 0", "derived", "dc_nameplate_bol_mwh", "Stage 2 result."),
        (FieldCode.EFFECTIVE_C_RATE, "Effective C Rate", "Effective C Rate", "C", ParameterDataType.FLOAT.value, False, StageCode.STAGE3.value, ">= 0", "derived", "effective_c_rate", "Stage 3 result."),
        (FieldCode.SOH_PROFILE_ID, "SOH Profile Id", "SOH Profile Id", UNIT_NONE, ParameterDataType.INTEGER.value, False, StageCode.STAGE3.value, ">= 0", "soh_profile_314_data", "soh_profile_id", "Selected SOH profile."),
        (FieldCode.RTE_PROFILE_ID, "RTE Profile Id", "RTE Profile Id", UNIT_NONE, ParameterDataType.INTEGER.value, False, StageCode.STAGE3.value, ">= 0", "rte_profile_314_data", "rte_profile_id", "Selected RTE profile."),
        (FieldCode.GUARANTEE_YEAR_POI_USABLE_MWH, "Guarantee Year POI Usable Energy", "Guarantee Year POI Usable Energy", UNIT_MWH, ParameterDataType.FLOAT.value, True, StageCode.DC_PIPELINE.value, ">= 0", "derived", "guarantee_year_poi_usable_mwh", "Guarantee checkpoint output."),
        (FieldCode.MARGIN_MWH, "Guarantee Margin", "Guarantee Margin", UNIT_MWH, ParameterDataType.FLOAT.value, True, StageCode.DC_PIPELINE.value, "float", "derived", "margin_mwh", "POI usable minus requirement."),
        (FieldCode.ITERATION_COUNT, "Iteration Count", "Iteration Count", UNIT_COUNT, ParameterDataType.INTEGER.value, False, StageCode.DC_PIPELINE.value, ">= 1", "derived", "iteration_count", "Guarantee oversize iteration count."),
    ]
    return [
        ParameterDefinitionSchema(
            field_code=field_code,
            display_name_en=display_name_en,
            display_name_zh=display_name_zh,
            unit=unit,
            data_type=data_type,
            nullable=nullable,
            required_for_stage=required_for_stage,
            validation_rule=validation_rule,
            source_sheet=source_sheet,
            legacy_field_name=legacy_field_name,
            remarks=remarks,
        )
        for (
            field_code,
            display_name_en,
            display_name_zh,
            unit,
            data_type,
            nullable,
            required_for_stage,
            validation_rule,
            source_sheet,
            legacy_field_name,
            remarks,
        ) in specs
    ]

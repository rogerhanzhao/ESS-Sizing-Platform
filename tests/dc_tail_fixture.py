"""Synthetic test/demo catalogue only; these are not CALB released parameters."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.dc_catalogue_revision_service import DcCatalogueRevisionService
from calb_sizing_tool.services.dc_configuration_variant_service import DcConfigurationVariantService
from calb_sizing_tool.services.dc_product_comparison_service import package_sha256
from calb_sizing_tool.services.product_admin_service import ProductAdminService


def make_tail_fixture(path, *, tail_power_kw=2500):
    url = 'sqlite:///' + Path(path).as_posix()
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    actor = AuthUser('synthetic-admin', 'synthetic-reviewer', 'Synthetic Reviewer', ['admin'])
    admin = ProductAdminService(url)
    cell = admin.create_cell(dict(cell_code='SYNTHETIC-314', model_name='Synthetic cell; not product evidence',
        chemistry='LFP', nominal_capacity_ah=314, nominal_voltage_v=3.2, is_active=True, is_published=True))
    admin.create_degradation_curve(dict(curve_code='SYNTHETIC-CURVE', product_cell_id=cell,
        condition_label='Synthetic mechanism fixture only', is_active=True, is_published=True))
    revisions = DcCatalogueRevisionService(actor, url)
    variants = DcConfigurationVariantService(actor, url)
    product_ids, revision_ids = {}, {}
    for strings, energy in ((12, 5.0159616), (10, 4.179968), (8, 3.3439744)):
        product_ids[strings] = admin.create_dc_block(dict(block_code=f'SYNTHETIC-{strings}STR',
            block_name=f'Synthetic {strings}-string container', product_cell_id=cell,
            block_form='container', container_type='20ft ISO container', cells_in_series=416,
            strings_in_parallel=strings, gross_energy_mwh=energy, voltage_min_v=1164.8,
            nominal_voltage_v=1331.2, voltage_max_v=1497.6,
            nominal_power_kw=tail_power_kw if strings == 10 else 2500,
            max_current_a=2500, max_c_rate=1, dimension_width_mm=2438,
            dimension_depth_mm=6058, dimension_height_mm=2896,
            default_degradation_curve_code='SYNTHETIC-CURVE', source_ref='Synthetic test source only',
            metadata_json=dict(configuration_role='standard_parent' if strings == 12 else 'engineering_variant'),
            is_active=True, is_published=True))
        revision_ids[strings] = revisions.create(product_ids[strings], 'SYNTHETIC-R1', 'Synthetic source capture')
        revisions.transition(revision_ids[strings], 'draft', 'parameter_review', 'Synthetic parameter checks')
        revisions.transition(revision_ids[strings], 'parameter_review', 'candidate_only', 'Synthetic test approval')
    relations = {}
    for strings in (10, 8):
        relation = variants.create(revision_ids[12], revision_ids[strings], 'SYNTHETIC-V1', dict(
            structural_evidence_ref='Synthetic structure', footprint_evidence_ref='Synthetic envelope',
            performance_evidence_ref='Synthetic performance'))
        variants.transition(relation, 'draft', 'candidate_only', 'Synthetic lineage review')
        relations[strings] = relation
    template = dict(schema_version=1, package_code='SYNTHETIC-PERFORMANCE', version='TEST-1',
        review_status='comparison_approved', reviewed_by='synthetic-reviewer',
        approval_ref='Synthetic mechanism test only; no engineering approval', measurement_boundary='DC',
        product_cell_id=cell,
        conditions=dict(dod_min_pct=90, dod_max_pct=100, temperature_min_c=20, temperature_max_c=30,
            standby_soc_min_pct=40, standby_soc_max_pct=60, project_life_max_years=2,
            rte_adjust_pp=0, rte_monotonic_enforce=True),
        soh_applicability=[dict(Profile_Id=1, c_rate_min=0, c_rate_max=1, cycles_min=300,
            cycles_max=400, evidence_ref='Synthetic applicability')],
        rte_applicability=[dict(Profile_Id=1, c_rate_min=0, c_rate_max=1, cycles_min=300,
            cycles_max=400, evidence_ref='Synthetic applicability')],
        tables=dict(soh_profile=[dict(Profile_Id=1, C_Rate=0.2, Cycles_Per_Year=365)],
            soh_curve=[dict(Profile_Id=1, Life_Year_Index=year, Soh_Dc_Pct=soh)
                       for year, soh in enumerate((100, 95, 90))],
            rte_profile=[dict(Profile_Id=1, C_Rate=0.2)],
            rte_curve=[dict(Profile_Id=1, Soh_Band_Min_Pct=100, Soh_Band_Max_Pct=100, Rte_Dc_Pct=94),
                       dict(Profile_Id=1, Soh_Band_Min_Pct=0, Soh_Band_Max_Pct=100, Rte_Dc_Pct=93)]))
    packages, partitions = {}, {}
    for strings, revision in revision_ids.items():
        detail = revisions.inspect(revision)
        package = deepcopy(template)
        package['product_revision_sha256'] = detail['sha256']
        packages[revision] = package
        partitions[revision] = [dict(domain_label='Synthetic independent output', strings=strings,
            gross_energy_mwh=detail['snapshot']['product']['gross_energy_mwh'],
            nominal_power_kw=tail_power_kw if strings == 10 else 2500,
            max_current_a=2500, evidence_ref='Synthetic output definition only')]
    baseline = DcExcelMasterDataBundle(workbook_path=Path('SYNTHETIC.xlsx'), defaults={},
        df_blocks=pd.DataFrame([dict(Dc_Block_Code='SYNTHETIC-BASELINE', Dc_Block_Name='Synthetic baseline',
            Block_Form='container', Block_Nameplate_Capacity_Mwh=5, Is_Active=1, Is_Default_Option=1)]),
        df_soh_profile=pd.DataFrame(template['tables']['soh_profile']),
        df_soh_curve=pd.DataFrame(template['tables']['soh_curve']),
        df_rte_profile=pd.DataFrame(template['tables']['rte_profile']),
        df_rte_curve=pd.DataFrame(template['tables']['rte_curve']), raw_sheets={})
    case = SizingCaseInput(project_name='SYNTHETIC tail comparison', scenario_id='container_only',
        poi_power_req_mw=2, poi_energy_req_mwh=7.2, project_life_years=2, poi_guarantee_year=2,
        cycles_per_year=365, sc_time_months=3, dod_pct=95, dc_round_trip_efficiency_pct=94,
        eff_dc_cables=100, eff_pcs=100, eff_mvt=100, eff_ac_cables_sw_rmu=100, eff_hvt_others=100)
    return SimpleNamespace(url=url, actor=actor, admin=admin, revisions=revisions, variants=variants,
        product_ids=product_ids, revision_ids=revision_ids, relations=relations, packages=packages,
        digests={key: package_sha256(value) for key, value in packages.items()},
        partitions=partitions, baseline=baseline, case=case)

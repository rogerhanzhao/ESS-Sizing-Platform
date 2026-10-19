import pytest
from calb_sizing_tool.services.cabinet_ac_preview_service import build_cabinet_groups,build_candidates

CODE=['CALB_0.418MWh_CAB_8P']


@pytest.mark.parametrize('count,expected',[(1,[1]),(12,[12]),(13,[7,6]),(40,[10]*4),
                                         (41,[11,10,10,10]),(48,[12]*4),(49,[10,10,10,10,9])])
def test_group_mapping_covers_each_physical_cabinet_once(count,expected):
    p=build_cabinet_groups(count,round(count*.418,3),CODE)
    assert [g['cabinet_count'] for g in p['groups']]==expected
    assert [i for g in p['groups'] for i in g['cabinet_indices']]==list(range(1,count+1))
    assert all(g['output_domain_count']==1 and not g['capability_verified'] for g in p['groups'])


def test_48_cabinets_yields_four_pcs_not_48_and_preserves_energy():
    p=build_cabinet_groups(48,20.064,CODE)
    candidates=build_candidates(p,8)
    assert any(c['station_pcs_nameplate_mw']==8 for c in candidates)
    for c in candidates:
        assert c['pcs_count']==4
        assert sorted(i for b in c['ac_blocks'] for i in b['group_indices'])==[1,2,3,4]
        assert sum(b['cabinet_count'] for b in c['ac_blocks'])==48
        assert c['poi_deliverable_mw'] is None and not c['capability_verified']


def test_alternative_group_count_and_partial_ac_block():
    p=build_cabinet_groups(48,20.064,CODE,6)
    assert [g['cabinet_count'] for g in p['groups']]==[8]*6
    cs=build_candidates(p,8)
    assert any([b['pcs_count'] for b in c['ac_blocks']]==[4,2] for c in cs)


@pytest.mark.parametrize('args',[(48,20.064,['OTHER']), (48,20.064,CODE,3), (48,20.064,CODE,49),
                                (48,20,CODE), (0,0,CODE)])
def test_unsupported_inputs_are_not_silently_reinterpreted(args):
    with pytest.raises(ValueError):build_cabinet_groups(*args)


def _preview_page():
    from calb_sizing_tool.ui.cabinet_ac_preview import show
    show(48,20.064,['CALB_0.418MWh_CAB_8P'],8,16,'local-test')


def test_local_page_changes_group_count_without_creating_legacy_outputs():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_function(_preview_page,default_timeout=30).run()
    assert not app.exception
    assert app.number_input[0].value==4
    assert '4 × 2000 kW' in app.selectbox[0].format_func(app.selectbox[0].value)
    app.number_input[0].set_value(6).run()
    assert not app.exception
    assert any('8 / 8 / 8 / 8 / 8 / 8' in str(x.value) for x in app.caption)
    assert 'ac_output' not in app.session_state

def test_original_allocation_maps_each_group_to_one_pcs_and_hashes_membership():
    from calb_sizing_tool.services.cabinet_ac_preview_service import attach_cabinet_allocation
    from calb_sizing_tool.services.ac_sizing_service import build_dc_allocation_plan
    from calb_sizing_tool.services.ac_run_service import ac_configuration_hash
    plan = build_cabinet_groups(41,17.138,CODE)
    bound = attach_cabinet_allocation(plan,build_dc_allocation_plan(4,2,2,dc_block_output_circuits=1))
    assert [(g['ac_block_index'],g['pcs_index']) for g in bound['groups']] == [(1,1),(1,2),(2,1),(2,2)]
    assert [g['cabinet_count'] for g in bound['groups']] == [11,10,10,10]
    assert 'ac_block_index' not in plan['groups'][0]
    assert ac_configuration_hash({'cabinet_group_contract':bound}) != ac_configuration_hash({})
    with pytest.raises(ValueError,match='exactly one'):
        attach_cabinet_allocation(plan,build_dc_allocation_plan(4,1,2,dc_block_output_circuits=1))

@pytest.mark.parametrize('corruption', ['duplicate_cabinet','wrong_energy','duplicate_pcs','missing_group','version'])
def test_saved_contract_rejects_corrupted_mappings(corruption):
    from calb_sizing_tool.services.cabinet_ac_preview_service import attach_cabinet_allocation, validate_cabinet_contract
    from calb_sizing_tool.services.ac_sizing_service import build_dc_allocation_plan
    plan=attach_cabinet_allocation(build_cabinet_groups(48,20.064,CODE),
        build_dc_allocation_plan(4,2,2,dc_block_output_circuits=1))
    if corruption=='duplicate_cabinet': plan['groups'][1]['cabinet_indices'][0]=1
    elif corruption=='wrong_energy': plan['groups'][0]['nameplate_mwh']=99
    elif corruption=='duplicate_pcs': plan['groups'][1]['pcs_index']=1
    elif corruption=='missing_group': plan['groups'].pop()
    else: plan['contract_version']='unknown'
    with pytest.raises(ValueError): validate_cabinet_contract(plan,allocated=True)

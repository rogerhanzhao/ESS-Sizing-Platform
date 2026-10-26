from streamlit.testing.v1 import AppTest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.product_admin_service import ProductAdminService


def _catalogue_page(db_url):
    from calb_sizing_tool.services.product_admin_service import ProductAdminService
    from calb_sizing_tool.ui.admin_portal_view import _section_dc_block

    service = ProductAdminService(db_url)
    _section_dc_block(service, service.snapshot())


def test_original_dc_admin_form_preserves_catalogue_with_stale_pilot_flags(tmp_path, monkeypatch):
    for name in ('CALB_DC_CATALOGUE_REVIEW', 'CALB_DC_REVISION_REVIEW', 'CALB_DC_VARIANT_REVIEW'):
        monkeypatch.setenv(name, '1')
    db_url = f"sqlite:///{(tmp_path / 'catalogue.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    service = ProductAdminService(db_url)
    cell = service.create_cell(dict(cell_code='314-A', model_name='314Ah A', chemistry='LFP'))
    service.create_dc_block(dict(block_code='C12', block_name='12 string container',
                                product_cell_id=cell, block_form='container', gross_energy_mwh=5.0))
    before = service.snapshot()
    page = AppTest.from_function(_catalogue_page, args=(db_url,), default_timeout=30).run()
    assert not page.exception
    assert not any('parameter review' in item.label or 'local pilot' in item.label for item in page.expander)
    assert any(item.label == 'Add DC Block Template' for item in page.expander)
    assert any(item.label == 'Edit Selected DC Block Template' for item in page.expander)
    assert any(item.label == 'Save DC Block Template' for item in page.button)
    assert service.snapshot() == before


def test_experimental_dc_admin_review_is_hidden_by_default(tmp_path, monkeypatch):
    for name in ('CALB_DC_CATALOGUE_REVIEW', 'CALB_DC_REVISION_REVIEW', 'CALB_DC_VARIANT_REVIEW'):
        monkeypatch.delenv(name, raising=False)
    db_url = f"sqlite:///{(tmp_path / 'original-admin.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    page = AppTest.from_function(_catalogue_page, args=(db_url,), default_timeout=30).run()
    assert not page.exception
    assert not any('parameter review' in item.label or 'local pilot' in item.label for item in page.expander)


def test_admin_adapter_keeps_all_rows_and_existing_selection_flags(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'adapter.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    service = ProductAdminService(db_url)
    service.create_dc_block(dict(block_code='C10', block_name='10 string', block_form='container',
                                rated_capacity_kwh=4200, is_active=False, is_published=True))
    service.create_dc_block(dict(block_code='TAIL', block_name='Tail cabinet', block_form='cabinet',
                                gross_energy_mwh=0.418, is_active=True, is_published=False))
    frame = service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code')
    assert set(frame.index) == {'C10', 'TAIL'}
    assert frame.loc['C10', 'Block_Nameplate_Capacity_Mwh'] == 4.2
    assert frame.loc['C10', 'Is_Active'] == 0
    assert frame.loc['C10', 'Is_Default_Option'] == 1
    assert frame.loc['TAIL', 'Block_Form'] == 'cabinet'
    assert frame.loc['TAIL', 'Is_Default_Option'] == 0

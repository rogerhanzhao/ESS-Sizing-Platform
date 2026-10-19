import pandas as pd
import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.product_admin_service import ProductAdminService


@pytest.fixture
def service(tmp_path):
    url = f"sqlite:///{(tmp_path/'catalogue.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(url))
    return ProductAdminService(url)


def test_preview_then_import_json_flags_and_integer(service):
    frame = pd.DataFrame([dict(block_code=' AC1 ', block_name='Review', pcs_count='2.0',
                               metadata_json='{"rating_unit":"kVA"}', is_published='false')])
    preview = service.preview_import_from_df(frame)
    assert preview['errors'] == []
    assert service.snapshot()['ac_blocks'] == []
    result = service.import_records_from_df('ac_block', frame)
    assert result['imported'] == 1
    record = service.snapshot()['ac_blocks'][0]
    assert record['pcs_count'] == 2
    assert record['metadata_json'] == {'rating_unit':'kVA'}
    assert record['is_published'] is False
    assert record['block_code'] == 'AC1'


@pytest.mark.parametrize('field,value', [('pcs_count','2.5'),('pcs_count','inf'),
    ('pcs_count','bad'),('is_published','maybe'),('metadata_json','{broken'),
    ('metadata_json','[]')])
def test_bad_rows_do_not_write_and_report_physical_line(service,field,value):
    frame = pd.DataFrame([dict(block_code='A',block_name='Name',**{field:value})],index=['external'])
    result = service.import_records_from_df('ac_block',frame)
    assert result['imported']==0 and result['skipped']==1
    assert result['errors'][0].startswith('Row 2:')
    assert service.snapshot()['ac_blocks']==[]


def test_create_only_does_not_overwrite_existing_product(service):
    service.create_ac_block(dict(block_code='A',block_name='Original'))
    result=service.import_records_from_df('ac_block',pd.DataFrame([dict(block_code='A',block_name='Replacement')]))
    assert result['imported']==0
    assert "already exists" in result['errors'][0]
    assert 'INSERT INTO' not in result['errors'][0]
    assert 'sqlalchemy' not in result['errors'][0]
    assert service.snapshot()['ac_blocks'][0]['block_name']=='Original'


def test_duplicate_columns_and_blank_json_defaults(service):
    frame=pd.DataFrame([['A','B']],columns=['block_code','block_code'])
    assert service.preview_import_from_df(frame)['errors']
    assert service.import_records_from_df('ac_block',frame)['skipped']==1
    good=pd.DataFrame([dict(block_code='A',block_name='Name',metadata_json='',is_published='')])
    assert service.import_records_from_df('ac_block',good)['imported']==1
    assert service.snapshot()['ac_blocks'][0]['metadata_json']=={}

@pytest.mark.parametrize('suffix', ['csv','xlsx'])
def test_file_parser_rejects_duplicate_source_headers(suffix):
    import io
    from unittest.mock import patch
    from calb_sizing_tool.ui.admin_portal_view import _parse_upload
    if suffix == 'csv':
        file=io.BytesIO(b'block_code,block_code\nA,B\n')
    else:
        buf=io.BytesIO()
        pd.DataFrame([['block_code','block_code'],['A','B']]).to_excel(buf,index=False,header=False)
        file=io.BytesIO(buf.getvalue())
    file.name='duplicate.'+suffix
    with patch('calb_sizing_tool.ui.admin_portal_view.st.error') as error:
        assert _parse_upload(file) is None
        assert 'unique' in error.call_args.args[0]

import io
import json
import zipfile

import pytest

from tests.test_cabinet_sld_service import saved
from tests.test_cabinet_sld_renderer import cabinet_output
from calb_sizing_tool.services import cabinet_arrangement_service as service


def _payloads(bundle):
    return {a['artifact_kind']: a for a in bundle.artifacts}


def test_saved_package_switches_all_pages_without_render_or_write(saved, monkeypatch):
    url, output, child, _, _ = saved
    bundle = service.generate_cabinet_arrangement(output, selected_block=1, parent_run_id='dc',
        ac_run_id=child, register=True, db_url=url)
    original = _payloads(bundle)[service.PACKAGE_KIND]['content']
    import calb_diagrams.cabinet_arrangement as renderer
    def forbidden(*args, **kwargs): pytest.fail('Switching must not render or persist')
    monkeypatch.setattr(renderer, 'render_cabinet_arrangement', forbidden)
    monkeypatch.setattr(service, 'persist_artifacts', forbidden)
    for page in (2, 1, 2):
        bundle, failures = service.select_cabinet_arrangement_sheet(bundle, output, selected_block=page,
            parent_run_id='dc', ac_run_id=child)
        assert bundle is not None and not failures
        payloads = _payloads(bundle)
        assert payloads[service.PACKAGE_KIND]['content'] == original
        assert payloads['layout_svg']['file_name'] == f'cabinet_arrangement_ac_{page:03d}.concept.svg'
        svg = payloads['layout_svg']['content']
        assert (b'C001' in svg) == (page == 1)
        assert (b'C048' in svg) == (page == 2)
    restored, failures = service.restore_cabinet_arrangement(output, selected_block=2,
        parent_run_id='dc', ac_run_id=child, db_url=url)
    assert not failures and restored is not None
    assert _payloads(restored)['layout_svg']['content'] == _payloads(bundle)['layout_svg']['content']


def test_no_parent_sibling_or_changed_input_fallback(saved):
    url, output, child, other, sibling = saved
    service.generate_cabinet_arrangement(output, selected_block=1, parent_run_id='dc',
        ac_run_id=child, register=True, db_url=url)
    restored, failures = service.restore_cabinet_arrangement(other, selected_block=1,
        parent_run_id='dc', ac_run_id=sibling, db_url=url)
    assert restored is None and not failures
    with pytest.raises(ValueError, match='exact saved output'):
        service.restore_cabinet_arrangement(other, selected_block=1, parent_run_id='dc', ac_run_id=child, db_url=url)
    with pytest.raises(ValueError, match='does not belong'):
        service.restore_cabinet_arrangement(output, selected_block=1, parent_run_id='wrong', ac_run_id=child, db_url=url)


def test_guest_is_memory_only_and_svg_only_has_no_old_png(tmp_path, monkeypatch):
    monkeypatch.setenv('CALB_OUTPUTS_DIR', str(tmp_path / 'outputs'))
    def forbidden(**kwargs): pytest.fail('Guest wrote artifacts')
    def unavailable(_): raise ImportError('No rasterizer')
    monkeypatch.setattr(service, 'persist_artifacts', forbidden)
    monkeypatch.setattr(service, '_png', unavailable)
    bundle = service.generate_cabinet_arrangement(cabinet_output(), selected_block=1,
        parent_run_id='guest', register=False)
    for selected in (2, 1):
        bundle, failures = service.select_cabinet_arrangement_sheet(bundle, cabinet_output(),
            selected_block=selected, parent_run_id='guest')
        assert not failures and bundle is not None
        assert 'layout_png' not in _payloads(bundle)
    assert not (tmp_path / 'outputs').exists()


@pytest.mark.parametrize('mutation', ['missing', 'changed', 'manifest', 'undeclared'])
def test_corrupted_package_cannot_supply_preview(mutation):
    output = cabinet_output()
    bundle = service.build_cabinet_arrangement_package(output, parent_run_id='guest')
    payloads = _payloads(bundle)
    with zipfile.ZipFile(io.BytesIO(payloads[service.PACKAGE_KIND]['content'])) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    target = 'cabinet_arrangement_ac_002.concept.svg'
    if mutation == 'missing': files.pop(target)
    if mutation == 'changed': files[target] += b'changed'
    if mutation == 'manifest': files[service.MANIFEST_NAME] += b' '
    if mutation == 'undeclared': files['unexpected.svg'] = b'<svg/>'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in files.items(): archive.writestr(name, content)
    payloads[service.PACKAGE_KIND]['content'] = stream.getvalue()
    selected, failures = service.select_cabinet_arrangement_sheet(bundle, output,
        selected_block=2, parent_run_id='guest')
    assert selected is None and failures


def test_only_session_token_is_ignored_by_package_identity():
    output = cabinet_output()
    bundle = service.build_cabinet_arrangement_package(output, parent_run_id='guest')
    refreshed = {**output, 'source_ac_run_id': 'another UI execution'}
    selected, failures = service.select_cabinet_arrangement_sheet(bundle, refreshed,
        selected_block=2, parent_run_id='guest')
    assert selected is not None and not failures
    for changed in ({**output, 'grid_kv': 34}, {**output, 'project_name': 'Other project'}):
        selected, _ = service.select_cabinet_arrangement_sheet(bundle, changed,
            selected_block=2, parent_run_id='guest')
        assert selected is None

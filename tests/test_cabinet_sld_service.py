import io
import json
import warnings
import zipfile
from pathlib import Path

import pytest
from tests.test_cabinet_sld_renderer import cabinet_output
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import Project, SizingRun, ArtifactRegistry
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.ac_run_service import persist_ac_run
from calb_sizing_tool.services import cabinet_sld_service as service
from calb_sizing_tool.services.artifact_service import persist_artifacts, resolve_artifact_path
from calb_sizing_tool.plugins.base import ArtifactPayload


@pytest.fixture
def saved(tmp_path, monkeypatch):
    url=f"sqlite:///{(tmp_path/'cabinet.sqlite').as_posix()}"
    monkeypatch.setenv('CALB_OUTPUTS_DIR',str(tmp_path/'outputs'))
    with session_scope(url) as session:
        Base.metadata.create_all(session.get_bind())
        session.add(Project(project_id='p',project_code='P',project_name='Test'))
        session.flush()
        session.add(SizingRun(sizing_run_id='dc',project_id='p',run_type='dc_pipeline',status='succeeded'))
    output=cabinet_output()
    output.update(project_name='Cabinet review',source_run_id='dc',pcs_kw=2000,pcs_per_block=2,block_size_mw=4)
    first=persist_ac_run(dc_run_id='dc',ac_inputs={},ac_output=output,db_url=url)
    other=cabinet_output()
    other.update(project_name='Cabinet review',source_run_id='dc',total_ac_mw=10,pcs_kw=2500,pcs_per_block=2,block_size_mw=5)
    for row in other['ac_block_rows']: row['pcs_kw']=2500
    second=persist_ac_run(dc_run_id='dc',ac_inputs={},ac_output=other,db_url=url)
    return url,output,first.run_id,other,second.run_id


def _generate(saved, selected=1):
    url,output,run,_,_=saved
    return service.generate_cabinet_sld(output,selected_block=selected,parent_run_id='dc',ac_run_id=run,register=True,db_url=url)


def test_package_contains_all_sheets_and_restores_last_selected_sheet(saved):
    url,output,run,_,_=saved
    bundle=_generate(saved,2)
    assert bundle.metadata['document_status']=='concept' and bundle.metadata['not_for_construction']
    assert bundle.metadata['artifacts_registered']
    data={a['artifact_kind']:a['content'] for a in bundle.artifacts}
    assert data['sld_png'].startswith(b'\x89PNG')
    with zipfile.ZipFile(io.BytesIO(data['cabinet_sld_package_zip'])) as archive:
        assert len([name for name in archive.namelist() if name.endswith('.svg')])==2
        assert len([name for name in archive.namelist() if name.endswith('.png')])==2
    assert service.saved_cabinet_sld_block(output,parent_run_id='dc',ac_run_id=run,db_url=url)==2
    restored,failures=service.restore_cabinet_sld(output,selected_block=2,parent_run_id='dc',ac_run_id=run,db_url=url)
    assert not failures and restored is not None
    assert {a['artifact_kind']:a['content'] for a in restored.artifacts}==data


def test_no_parent_or_sibling_fallback_and_no_wrong_alternative_write(saved):
    url,output,run,other,second=saved
    _generate(saved)
    persist_artifacts(run_id='dc',artifacts=[ArtifactPayload('sld_svg','old.svg','image/svg+xml',b'<svg>container</svg>')],
                      plugin_id='old-container',plugin_version='1',db_url=url)
    restored,failures=service.restore_cabinet_sld(other,selected_block=1,parent_run_id='dc',ac_run_id=second,db_url=url)
    assert restored is None and not failures
    with pytest.raises(ValueError,match='exact saved output'):
        service.generate_cabinet_sld(other,selected_block=1,parent_run_id='dc',ac_run_id=run,register=True,db_url=url)
    with pytest.raises(ValueError,match='does not belong'):
        service.generate_cabinet_sld(output,selected_block=1,parent_run_id='different',ac_run_id=run,register=True,db_url=url)


def test_guest_generation_does_not_persist_or_create_outputs(tmp_path,monkeypatch):
    monkeypatch.setenv('CALB_OUTPUTS_DIR',str(tmp_path/'outputs'))
    monkeypatch.setattr(service,'persist_artifacts',lambda **kwargs: pytest.fail('Guest wrote artifacts'))
    bundle=service.generate_cabinet_sld(cabinet_output(),selected_block=1,parent_run_id='guest',register=False)
    assert bundle.metadata['artifacts_registered'] is False
    assert not (tmp_path/'outputs').exists()


def _artifact_path(url,run,kind):
    with session_scope(url) as session:
        row=session.query(ArtifactRegistry).filter_by(sizing_run_id=run,artifact_kind=kind).one()
        return resolve_artifact_path(row.file_path)


def test_changed_svg_and_malformed_manifest_are_rejected(saved):
    url,output,run,_,_=saved
    _generate(saved)
    _artifact_path(url,run,'sld_svg').write_bytes(b'<svg>wrong sheet</svg>')
    restored,failures=service.restore_cabinet_sld(output,selected_block=1,parent_run_id='dc',ac_run_id=run,db_url=url)
    assert restored is None and failures
    _artifact_path(url,run,'sld_readiness_manifest_json').write_text('[]')
    restored,failures=service.restore_cabinet_sld(output,selected_block=1,parent_run_id='dc',ac_run_id=run,db_url=url)
    assert restored is None and failures


def test_svg_only_generation_does_not_resurrect_previous_png(saved,monkeypatch):
    url,output,run,_,_=saved
    _generate(saved)
    def unavailable(_): raise ImportError('Cairo unavailable')
    monkeypatch.setattr(service,'_png',unavailable)
    bundle=_generate(saved)
    assert 'sld_png' not in {a['artifact_kind'] for a in bundle.artifacts}
    restored,failures=service.restore_cabinet_sld(output,selected_block=1,parent_run_id='dc',ac_run_id=run,db_url=url)
    assert not failures and restored is not None
    assert 'sld_png' not in {a['artifact_kind'] for a in restored.artifacts}
    for selected in (2, 1):
        restored, failures = service.select_cabinet_sld_sheet(
            restored, output, selected_block=selected, parent_run_id='dc', ac_run_id=run)
        assert restored is not None and not failures
        assert 'sld_png' not in {a['artifact_kind'] for a in restored.artifacts}
        assert next(a for a in restored.artifacts if a['artifact_kind'] == 'sld_svg')['file_name'] == (
            f'cabinet_sld_ac_{selected:03d}.concept.svg')


def test_restored_parent_matches_only_identical_saved_child(saved):
    url,output,run,other,second=saved
    assert service.matching_saved_cabinet_alternative(output,parent_run_id='dc',db_url=url)==run
    assert service.matching_saved_cabinet_alternative(other,parent_run_id='dc',db_url=url)==second
    changed={**output,'project_name':'Changed since save'}
    assert service.matching_saved_cabinet_alternative(changed,parent_run_id='dc',db_url=url) is None


@pytest.fixture(scope='module')
def generated_package():
    """A real two-sheet SVG/PNG package shared only by immutable test reads."""
    output = cabinet_output()
    output.update(project_name='Sheet selection review', source_run_id='dc', source_ac_run_id='session-before')
    bundle = service.build_cabinet_sld_package(
        output, selected_block=1, parent_run_id='dc', ac_run_id='saved-child')
    return output, bundle


def _payloads(bundle):
    return {artifact['artifact_kind']: artifact for artifact in bundle.artifacts}


def test_sheet_roundtrip_uses_verified_svg_and_png_without_render_or_write(generated_package, monkeypatch):
    output, bundle = generated_package
    initial = _payloads(bundle)
    package = initial['cabinet_sld_package_zip']['content']
    manifest = initial['sld_readiness_manifest_json']['content']
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        expected = {name: archive.read(name) for name in archive.namelist()}

    def forbidden(*args, **kwargs):
        pytest.fail('Selecting an existing sheet must neither render nor persist')

    import calb_diagrams.cabinet_sld as renderer
    monkeypatch.setattr(renderer, 'render_cabinet_sld', forbidden)
    monkeypatch.setattr(service, '_png', forbidden)
    monkeypatch.setattr(service, 'persist_artifacts', forbidden)
    current = bundle
    for selected in (2, 1, 2, 1):
        current, failures = service.select_cabinet_sld_sheet(
            current, output, selected_block=selected, parent_run_id='dc', ac_run_id='saved-child')
        assert current is not None and not failures
        payloads = _payloads(current)
        stem = f'cabinet_sld_ac_{selected:03d}.concept'
        for kind, suffix in [('sld_svg', '.svg'), ('sld_png', '.png')]:
            assert payloads[kind]['file_name'] == stem + suffix
            assert payloads[kind]['content'] == expected[stem + suffix]
        svg = payloads['sld_svg']['content'].decode()
        assert ('id="cabinet-1"' in svg) == (selected == 1)
        assert ('id="cabinet-48"' in svg) == (selected == 2)
        assert payloads['cabinet_sld_package_zip']['content'] == package
        assert payloads['sld_readiness_manifest_json']['content'] == manifest
        assert current.metadata['selected_ac_block'] == selected
        assert current.metadata['generated_selected_ac_block'] == 1
        assert current.metadata['artifacts_registered'] is False


def test_transient_token_change_reuses_saved_package_but_real_input_or_child_change_does_not(saved):
    url, output, run, _, other_run = saved
    _generate(saved)
    changed_token = {**output, 'source_ac_run_id': 'new-session-token'}
    refreshed = persist_ac_run(dc_run_id='dc', ac_inputs={}, ac_output=changed_token, db_url=url)
    assert refreshed.reused and refreshed.run_id == run
    assert service.input_signature(output, 1, 'dc', run) == service.input_signature(changed_token, 1, 'dc', run)
    assert service.matching_saved_cabinet_alternative(changed_token, parent_run_id='dc', db_url=url) == run
    # The old parent runtime can still identify its child after only its token was refreshed.
    assert service.matching_saved_cabinet_alternative(output, parent_run_id='dc', db_url=url) == run
    restored, failures = service.restore_cabinet_sld(
        changed_token, selected_block=2, parent_run_id='dc', ac_run_id=run, db_url=url)
    assert restored is not None and not failures
    assert _payloads(restored)['sld_svg']['file_name'] == 'cabinet_sld_ac_002.concept.svg'
    for changed_output, parent, child in (
        (changed_token, 'dc', other_run),
        (changed_token, 'other-parent', run),
        ({**changed_token, 'grid_kv': 34}, 'dc', run),
        ({**changed_token, 'source_run_id': 'other-parent'}, 'dc', run),
    ):
        rejected, _ = service.select_cabinet_sld_sheet(
            restored, changed_output, selected_block=1, parent_run_id=parent, ac_run_id=child)
        assert rejected is None
    with pytest.raises(ValueError, match='exact saved output'):
        service.restore_cabinet_sld(
            {**changed_token, 'grid_kv': 34}, selected_block=1,
            parent_run_id='dc', ac_run_id=run, db_url=url)


def _with_package(bundle, package):
    copied = bundle.model_copy(deep=True)
    _payloads(copied)['cabinet_sld_package_zip']['content'] = package
    return copied


@pytest.mark.parametrize('mutation', ['duplicate', 'missing', 'undeclared', 'tampered', 'manifest', 'truncated'])
def test_invalid_zip_cannot_supply_another_preview_sheet(generated_package, mutation):
    output, bundle = generated_package
    package = _payloads(bundle)['cabinet_sld_package_zip']['content']
    if mutation == 'truncated':
        changed = package[:-40]
    else:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            files = [(name, archive.read(name)) for name in archive.namelist()]
        target = 'cabinet_sld_ac_002.concept.svg'
        if mutation == 'duplicate':
            files.append((target, dict(files)[target]))
        elif mutation == 'missing':
            files = [(name, content) for name, content in files if name != target]
        elif mutation == 'undeclared':
            files.append(('extra-undeclared.svg', b'<svg/>'))
        elif mutation == 'tampered':
            files = [(name, b'<svg>wrong sheet</svg>' if name == target else content) for name, content in files]
        elif mutation == 'manifest':
            files = [(name, content + b' ' if name.endswith('.json') else content) for name, content in files]
        stream = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)  # Intentionally create a duplicate ZIP member.
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, content in files:
                    archive.writestr(name, content)
        changed = stream.getvalue()
    selected, failures = service.select_cabinet_sld_sheet(
        _with_package(bundle, changed), output, selected_block=2, parent_run_id='dc', ac_run_id='saved-child')
    assert selected is None and failures


@pytest.mark.parametrize('kind,suffix', [('sld_svg', '.svg'), ('sld_png', '.png')])
def test_independent_preview_file_must_match_its_current_page_before_switch(generated_package, kind, suffix):
    output, original = generated_package
    changed = original.model_copy(deep=True)
    payloads = _payloads(changed)
    with zipfile.ZipFile(io.BytesIO(payloads['cabinet_sld_package_zip']['content'])) as archive:
        payloads[kind]['content'] = archive.read('cabinet_sld_ac_002.concept' + suffix)
    selected, failures = service.select_cabinet_sld_sheet(
        changed, output, selected_block=2, parent_run_id='dc', ac_run_id='saved-child')
    assert selected is None and failures


@pytest.mark.parametrize('selected', [True, 1.0, '1', 0, -1, 3])
def test_invalid_sheet_identifier_is_rejected(generated_package, selected):
    output, bundle = generated_package
    selected_bundle, failures = service.select_cabinet_sld_sheet(
        bundle, output, selected_block=selected, parent_run_id='dc', ac_run_id='saved-child')
    assert selected_bundle is None and failures

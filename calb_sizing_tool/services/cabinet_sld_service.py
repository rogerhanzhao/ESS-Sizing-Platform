"""Cabinet-only SLD package; existing container pipeline remains independent."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.schemas.diagram_inputs import DiagramArtifactBundle
from calb_sizing_tool.services.artifact_service import persist_artifacts, load_artifact_bytes_with_failures

PLUGIN_ID = 'cabinet_sld_v1'
VERSION = '1.0.1'
KINDS = ['sld_svg', 'sld_png', 'sld_readiness_manifest_json', 'cabinet_sld_package_zip']


def _drawing_input(output: dict) -> dict:
    """Exclude only the transient session token; the real saved child ID stays bound."""
    return {key: value for key, value in output.items() if key != 'source_ac_run_id'}


def input_signature(output: dict, selected_block: int, parent_run_id: str, ac_run_id: str | None) -> str:
    raw = json.dumps(dict(output=_drawing_input(output), selected_block=selected_block, parent_run_id=parent_run_id,
                          ac_run_id=ac_run_id, renderer_version=VERSION), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def _png(svg: bytes) -> bytes:
    import cairosvg
    from calb_sizing_tool.common.render_lock import RENDER_LOCK
    with RENDER_LOCK:
        return cairosvg.svg2png(bytestring=svg, background_color='white')


def _verify_alternative(parent_run_id, ac_run_id, db_url, output):
    from calb_sizing_tool.infra.db.session import session_scope
    from calb_sizing_tool.infra.db.models.sizing_run import SizingRun
    if not ac_run_id:
        raise ValueError('Save and select an AC alternative before generating cabinet SLD artifacts')
    with session_scope(db_url) as session:
        row = session.get(SizingRun, ac_run_id)
        if row is None or row.run_type != 'ac_sizing' or row.parent_run_id != parent_run_id:
            raise ValueError('The selected AC alternative does not belong to this DC result')
        from calb_sizing_tool.repositories.run_repository import RunRepository
        from calb_sizing_tool.services.ac_run_service import AC_OUTPUT_SNAPSHOT_KIND
        stored = RunRepository(session).get_latest_output_snapshot_by_kind(ac_run_id, AC_OUTPUT_SNAPSHOT_KIND)
        if stored is None or _drawing_input(stored.snapshot_json) != _drawing_input(output) or output.get('source_run_id') != parent_run_id:
            raise ValueError('Cabinet SLD must use the exact saved output of this AC alternative')



def build_cabinet_sld_package(output: dict, *, selected_block: int = 1, parent_run_id: str = '',
                              ac_run_id: str | None = None) -> DiagramArtifactBundle:
    if type(selected_block) is not int or selected_block < 1:
        raise ValueError('The selected AC Block must be a positive integer')
    from calb_diagrams.cabinet_sld import render_cabinet_sld
    rendered = render_cabinet_sld(output, project_name=str(output.get('project_name') or output.get('source_project_name') or 'CALB ESS Project'))
    pages = rendered['pages']
    chosen = next((p for p in pages if p['ac_block_index'] == selected_block), None)
    if chosen is None:
        raise ValueError('The selected AC Block is not present in this cabinet configuration')
    signature = input_signature(output, selected_block, parent_run_id, ac_run_id)
    metadata = dict(artifact_mode='concept', document_status='concept', not_for_construction=True,
                    renderer_mode=PLUGIN_ID, renderer_version=VERSION, renderer_lineage=PLUGIN_ID,
                    contract_version=output['cabinet_group_contract']['contract_version'],
                    run_id=parent_run_id, artifact_run_id=ac_run_id,
                    source_run_id=parent_run_id, source_ac_run_id=ac_run_id, selected_ac_block=selected_block,
                    input_hash=signature, signature=signature, physical_cabinet_count=output['cabinet_group_contract']['physical_cabinet_count'])
    artifacts = []
    files = {}
    raster_warnings = []
    for page in pages:
        index = page['ac_block_index']
        stem = f'cabinet_sld_ac_{index:03d}.concept'
        svg = page['svg'].encode('utf-8')
        files[stem + '.svg'] = svg
        try:
            png = _png(svg)
        except (ImportError, OSError) as exc:
            png = None
            raster_warnings.append(f'AC Block {index}: PNG conversion is unavailable; SVG remains available.')
        if png:
            files[stem + '.png'] = png
        if index == selected_block:
            artifacts.append(ArtifactPayload('sld_svg', stem + '.svg', 'image/svg+xml', svg, dict(metadata)))
            if png:
                artifacts.append(ArtifactPayload('sld_png', stem + '.png', 'image/png', png, dict(metadata)))
    manifest = dict(metadata, plugin_id=PLUGIN_ID, page_count=len(pages),
                    warnings=list(rendered['warnings']) + raster_warnings, topology=rendered['topology'],
                    formal_readiness={'ready': False, 'basis': 'cabinet_concept_pending_engineering_confirmation'},
                    files={name: hashlib.sha256(content).hexdigest() for name, content in files.items()})
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')
    files['cabinet_sld_readiness_manifest.concept.json'] = manifest_bytes
    artifacts.append(ArtifactPayload('sld_readiness_manifest_json', 'cabinet_sld_readiness_manifest.concept.json',
                                     'application/json', manifest_bytes, dict(metadata)))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for name, content in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(info, content)
    artifacts.append(ArtifactPayload('cabinet_sld_package_zip', 'cabinet_sld_package.concept.zip',
                                     'application/zip', archive.getvalue(), dict(metadata)))
    for artifact in artifacts:
        artifact.metadata['content_hash'] = hashlib.sha256(artifact.content).hexdigest()
    return DiagramArtifactBundle(plugin_id=PLUGIN_ID, plugin_version=VERSION,
        run_id=ac_run_id or parent_run_id or 'guest-session',
        metadata={**metadata, 'warnings': manifest['warnings'], 'artifacts_registered': False},
        artifacts=[a.__dict__ for a in artifacts])


def generate_cabinet_sld(output: dict, *, selected_block: int, parent_run_id: str,
                          ac_run_id: str | None = None, register: bool = False,
                          actor: str | None = None, db_url: str | None = None) -> DiagramArtifactBundle:
    if register:
        _verify_alternative(parent_run_id, ac_run_id, db_url, output)
    bundle = build_cabinet_sld_package(output, selected_block=selected_block,
                                      parent_run_id=parent_run_id, ac_run_id=ac_run_id)
    if register:
        persist_artifacts(run_id=ac_run_id, artifacts=[ArtifactPayload(**a) for a in bundle.artifacts],
                          plugin_id=PLUGIN_ID, plugin_version=VERSION, actor=actor, db_url=db_url,
                          source_ref='cabinet_sld_service')
        bundle.metadata['artifacts_registered'] = True
    return bundle


def restore_cabinet_sld(output: dict, *, selected_block: int, parent_run_id: str,
                         ac_run_id: str, db_url: str | None = None):
    _verify_alternative(parent_run_id, ac_run_id, db_url, output)
    content, failures = load_artifact_bytes_with_failures(ac_run_id, KINDS, db_url=db_url, include_ancestors=False)
    raw = content.get('sld_readiness_manifest_json')
    if not raw:
        return None, failures
    try:
        manifest = json.loads(raw)
    except (ValueError, TypeError):
        return None, failures + ['The saved cabinet SLD manifest could not be read. Regenerate the drawing.']
    if not isinstance(manifest, dict):
        return None, failures + ['The saved cabinet SLD manifest has an invalid structure. Regenerate the drawing.']
    # Registry rows contain the original preview. Other sheets are read only from
    # that same child's verified all-sheet package, never from another run.
    bundle = DiagramArtifactBundle(plugin_id=PLUGIN_ID, plugin_version=VERSION, run_id=ac_run_id,
        metadata={**manifest, 'artifacts_registered': True},
        artifacts=[dict(artifact_kind=kind, content=data) for kind, data in content.items()])
    selected, selection_failures = select_cabinet_sld_sheet(bundle, output, selected_block=selected_block,
        parent_run_id=parent_run_id, ac_run_id=ac_run_id)
    return selected, failures + selection_failures


def select_cabinet_sld_sheet(bundle, output, *, selected_block, parent_run_id, ac_run_id=None):
    """Select a verified sheet without rendering or writing files/registry rows.

    The package and its manifest keep their original bytes. Only the preview
    metadata changes, with the original generation choice recorded separately.
    This works for both a guest's in-memory bundle and a saved child package.
    """
    blocks = {group['ac_block_index'] for group in output['cabinet_group_contract']['groups']}
    if type(selected_block) is not int or selected_block not in blocks:
        return None, ['The requested AC Block is not part of this cabinet configuration.']
    content = {a['artifact_kind']: a['content'] for a in bundle.artifacts}
    raw = content.get('sld_readiness_manifest_json')
    try:
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict):
            raise ValueError('Invalid manifest structure')
        generated = manifest['selected_ac_block']
        if type(generated) is not int or generated not in blocks:
            raise ValueError('Invalid generated page')
    except (ValueError, TypeError, KeyError):
        return None, ['The cabinet SLD manifest is invalid. Regenerate the drawing.']
    expected = input_signature(output, generated, parent_run_id, ac_run_id)
    if (bundle.plugin_id != PLUGIN_ID or manifest.get('plugin_id') != PLUGIN_ID
            or manifest.get('renderer_version') != VERSION or manifest.get('signature') != expected
            or manifest.get('source_run_id') != parent_run_id or manifest.get('source_ac_run_id') != ac_run_id):
        return None, []  # Changed inputs/renderer: the old drawing is not reusable.
    current = bundle.metadata.get('selected_ac_block')
    if (type(current) is not int or current not in blocks or bundle.metadata.get('signature') !=
            input_signature(output, current, parent_run_id, ac_run_id)):
        return None, ['The cabinet SLD preview does not match this AC alternative. Regenerate the drawing.']
    files = manifest['files']
    svg_names = {f'cabinet_sld_ac_{index:03d}.concept.svg' for index in blocks}
    allowed_names = svg_names | {name[:-4] + '.png' for name in svg_names}
    if (manifest.get('page_count') != len(blocks) or not svg_names.issubset(files)
            or not set(files).issubset(allowed_names)):
        return None, ['The cabinet SLD package does not contain the expected AC Block sheets. Regenerate the drawing.']
    current_stem = f'cabinet_sld_ac_{current:03d}.concept'
    if 'sld_svg' not in content:
        return None, ['The saved cabinet SLD sheet is unavailable. Regenerate the drawing.']
    for kind, suffix in [('sld_svg', '.svg'), ('sld_png', '.png')]:
        name = current_stem + suffix
        if kind == 'sld_png' and name not in files:
            content.pop(kind, None)  # An earlier registered PNG must not reappear.
        if kind in content and hashlib.sha256(content[kind]).hexdigest() != files.get(name):
            return None, ['Saved cabinet SLD content does not match its manifest. Regenerate the drawing.']
    stem = f'cabinet_sld_ac_{selected_block:03d}.concept'
    package = content.get('cabinet_sld_package_zip')
    if package:
        try:
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                members = archive.namelist()
                if (len(members) != len(set(members)) or set(members) !=
                        set(files) | {'cabinet_sld_readiness_manifest.concept.json'}):
                    raise ValueError('Package member mismatch')
                if archive.read('cabinet_sld_readiness_manifest.concept.json') != raw:
                    raise ValueError('Package manifest mismatch')
                verified = {}
                for name, digest in files.items():
                    data = archive.read(name)
                    if hashlib.sha256(data).hexdigest() != digest:
                        raise ValueError('Package file hash mismatch')
                    verified[name] = data
                content['sld_svg'] = verified[stem + '.svg']
                content.pop('sld_png', None)
                if stem + '.png' in verified:
                    content['sld_png'] = verified[stem + '.png']
        except (ValueError, KeyError, zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
            return None, ['Saved cabinet SLD package is incomplete or changed. Regenerate the drawing.']
    elif selected_block != current:
        return None, ['The all-sheet cabinet SLD package is unavailable. Regenerate it to preview another AC Block.']
    signature = input_signature(output, selected_block, parent_run_id, ac_run_id)
    metadata = {**manifest, 'selected_ac_block': selected_block, 'generated_selected_ac_block': generated,
                'signature': signature, 'input_hash': signature,
                'artifacts_registered': bool(bundle.metadata.get('artifacts_registered'))}
    names = {'sld_svg': (stem + '.svg', 'image/svg+xml'), 'sld_png': (stem + '.png', 'image/png'),
             'sld_readiness_manifest_json': ('cabinet_sld_readiness_manifest.concept.json', 'application/json'),
             'cabinet_sld_package_zip': ('cabinet_sld_package.concept.zip', 'application/zip')}
    artifacts = [ArtifactPayload(kind, *names[kind], data,
        metadata={**metadata, 'content_hash': hashlib.sha256(data).hexdigest()}).__dict__
        for kind, data in content.items() if kind in names]
    return DiagramArtifactBundle(plugin_id=PLUGIN_ID, plugin_version=VERSION, run_id=bundle.run_id,
        metadata=metadata, artifacts=artifacts), []


def saved_cabinet_sld_block(output, *, parent_run_id, ac_run_id, db_url=None):
    """Restore the last selected sheet only when it matches this exact AC input."""
    content, _ = load_artifact_bytes_with_failures(ac_run_id, ['sld_readiness_manifest_json'],
        db_url=db_url, include_ancestors=False)
    try:
        manifest = json.loads(content.get('sld_readiness_manifest_json', b''))
        if not isinstance(manifest, dict):
            return None
        block = manifest['selected_ac_block']
        if type(block) is int and manifest.get('plugin_id') == PLUGIN_ID and manifest.get('signature') == input_signature(
            output, block, parent_run_id, ac_run_id):
            return block
    except (ValueError, KeyError, TypeError):
        pass
    return None


def matching_saved_cabinet_alternative(output, *, parent_run_id, db_url=None):
    """Resolve a restored parent runtime only to one exactly identical saved child."""
    from calb_sizing_tool.infra.db.session import session_scope
    from calb_sizing_tool.repositories.run_repository import RunRepository
    from calb_sizing_tool.services.ac_run_service import AC_OUTPUT_SNAPSHOT_KIND, AC_RUN_TYPE
    matches=[]
    with session_scope(db_url) as session:
        repo=RunRepository(session)
        for child in repo.list_child_runs(parent_run_id,run_type=AC_RUN_TYPE):
            snapshot=repo.get_latest_output_snapshot_by_kind(child.sizing_run_id,AC_OUTPUT_SNAPSHOT_KIND)
            if snapshot is not None and _drawing_input(snapshot.snapshot_json)==_drawing_input(output) and output.get('source_run_id')==parent_run_id:
                matches.append(child.sizing_run_id)
    return matches[0] if len(matches)==1 else None

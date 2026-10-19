"""Concept arrangement packages owned by one saved cabinet AC alternative.

The immutable all-sheet ZIP is the source for preview, downloads and reports.
Generic layout PNG/SVG rows are convenience exports, never a fallback source.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.schemas.diagram_inputs import DiagramArtifactBundle
from calb_sizing_tool.services.artifact_service import persist_artifacts, load_artifact_bytes_with_failures
from calb_sizing_tool.services.cabinet_document_service import document_signature, verify_cabinet_ac_source

PLUGIN_ID = 'cabinet_arrangement_v1'
VERSION = '1.0.0'
MANIFEST_KIND = 'cabinet_arrangement_manifest_json'
PACKAGE_KIND = 'cabinet_arrangement_package_zip'
MANIFEST_NAME = 'cabinet_arrangement_manifest.concept.json'
PACKAGE_NAME = 'cabinet_arrangement_package.concept.zip'


def input_signature(output, parent_run_id, ac_run_id, installation_basis=None):
    return document_signature(output, parent_run_id, ac_run_id, plugin_id=PLUGIN_ID,
                              version=VERSION, installation_basis=installation_basis)


def _png(svg):
    import cairosvg
    from calb_sizing_tool.common.render_lock import RENDER_LOCK
    with RENDER_LOCK:
        return cairosvg.svg2png(bytestring=svg, background_color='white')


def _stem(index):
    return f'cabinet_arrangement_ac_{index:03d}.concept'


def build_cabinet_arrangement_package(output, *, selected_block=1, parent_run_id='', ac_run_id=None,
                                      installation_basis=None):
    from calb_diagrams.cabinet_arrangement import render_cabinet_arrangement
    if type(selected_block) is not int or selected_block < 1:
        raise ValueError('The selected AC Block must be a positive integer')
    rendered = render_cabinet_arrangement(output,
        project_name=str(output.get('project_name') or output.get('source_project_name') or 'CALB ESS Project'),
        installation_basis=installation_basis)
    if selected_block not in {page['ac_block_index'] for page in rendered['pages']}:
        raise ValueError('The selected AC Block is not part of this cabinet arrangement')
    signature = input_signature(output, parent_run_id, ac_run_id, installation_basis)
    metadata = dict(plugin_id=PLUGIN_ID, renderer_version=VERSION, signature=signature, input_hash=signature,
                    document_status='concept', artifact_mode='concept', not_for_construction=True,
                    source_run_id=parent_run_id, source_ac_run_id=ac_run_id,
                    selected_ac_block=selected_block, installation_basis=installation_basis)
    files = {}
    warnings = list(rendered['warnings'])
    for page in rendered['pages']:
        stem = _stem(page['ac_block_index'])
        svg = page['svg'].encode('utf-8')
        files[stem + '.svg'] = svg
        try:
            files[stem + '.png'] = _png(svg)
        except (ImportError, OSError):
            warnings.append(f"AC Block {page['ac_block_index']}: PNG conversion is unavailable; SVG remains available.")
    manifest = {**metadata, 'page_count': len(rendered['pages']), 'schedule': rendered['schedule'],
                'warnings': warnings, 'formal_readiness': {'ready': False, 'basis': 'concept_arrangement'},
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    raw = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        for name, data in {**files, MANIFEST_NAME: raw}.items():
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(item, data)
    initial = DiagramArtifactBundle(plugin_id=PLUGIN_ID, plugin_version=VERSION,
        run_id=ac_run_id or parent_run_id or 'guest-session',
        metadata={**metadata, 'artifacts_registered': False}, artifacts=[
            ArtifactPayload(MANIFEST_KIND, MANIFEST_NAME, 'application/json', raw).__dict__,
            ArtifactPayload(PACKAGE_KIND, PACKAGE_NAME, 'application/zip', archive.getvalue()).__dict__])
    bundle, failures = select_cabinet_arrangement_sheet(initial, output, selected_block=selected_block,
        parent_run_id=parent_run_id, ac_run_id=ac_run_id, installation_basis=installation_basis)
    if bundle is None:
        raise ValueError('; '.join(failures) or 'The generated arrangement package failed verification')
    return bundle


def select_cabinet_arrangement_sheet(bundle, output, *, selected_block, parent_run_id, ac_run_id=None,
                                      installation_basis=None):
    blocks = {group['ac_block_index'] for group in output['cabinet_group_contract']['groups']}
    if type(selected_block) is not int or selected_block not in blocks:
        return None, ['The requested AC Block is not part of this cabinet configuration.']
    payloads = {item['artifact_kind']: item['content'] for item in bundle.artifacts}
    raw = payloads.get(MANIFEST_KIND)
    try:
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict):
            raise ValueError('Invalid manifest')
        generated = manifest['selected_ac_block']
        if type(generated) is not int or generated not in blocks:
            raise ValueError('Invalid generated sheet')
    except (ValueError, TypeError, KeyError):
        return None, ['The saved cabinet arrangement manifest is invalid. Regenerate the arrangement.']
    signature = input_signature(output, parent_run_id, ac_run_id, installation_basis)
    if (bundle.plugin_id != PLUGIN_ID or manifest.get('plugin_id') != PLUGIN_ID
            or manifest.get('renderer_version') != VERSION or manifest.get('signature') != signature
            or manifest.get('source_run_id') != parent_run_id or manifest.get('source_ac_run_id') != ac_run_id
            or manifest.get('installation_basis') != installation_basis):
        return None, []
    names = set(manifest['files'])
    svg_names = {_stem(index) + '.svg' for index in blocks}
    if (type(manifest.get('page_count')) is not int or manifest['page_count'] != len(blocks)
            or not svg_names.issubset(names) or not names.issubset(svg_names | {name[:-4]+'.png' for name in svg_names})):
        return None, ['The arrangement package does not contain all expected AC Block sheets. Regenerate it.']
    package = payloads.get(PACKAGE_KIND)
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            members = archive.namelist()
            if len(members) != len(set(members)) or set(members) != names | {MANIFEST_NAME}:
                raise ValueError('Package members changed')
            if archive.read(MANIFEST_NAME) != raw:
                raise ValueError('Package manifest changed')
            contents = {name: archive.read(name) for name in names}
            if any(hashlib.sha256(data).hexdigest() != manifest['files'][name] for name, data in contents.items()):
                raise ValueError('Package hashes changed')
    except (TypeError, ValueError, KeyError, zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
        return None, ['The saved arrangement package is unavailable, incomplete or changed. Regenerate it.']
    metadata = {**manifest, 'selected_ac_block': selected_block,
                'generated_selected_ac_block': manifest['selected_ac_block'],
                'artifacts_registered': bool(bundle.metadata.get('artifacts_registered'))}
    artifacts = [ArtifactPayload(MANIFEST_KIND, MANIFEST_NAME, 'application/json', raw, dict(metadata)),
                 ArtifactPayload(PACKAGE_KIND, PACKAGE_NAME, 'application/zip', package, dict(metadata))]
    for suffix, kind, mime in [('.svg', 'layout_svg', 'image/svg+xml'), ('.png', 'layout_png', 'image/png')]:
        name = _stem(selected_block) + suffix
        if name in contents:
            artifacts.append(ArtifactPayload(kind, name, mime, contents[name], dict(metadata)))
    for item in artifacts:
        item.metadata['content_hash'] = hashlib.sha256(item.content).hexdigest()
    return DiagramArtifactBundle(plugin_id=PLUGIN_ID, plugin_version=VERSION, run_id=bundle.run_id,
        metadata=metadata, artifacts=[item.__dict__ for item in artifacts]), []


def generate_cabinet_arrangement(output, *, selected_block, parent_run_id, ac_run_id=None,
                                  register=False, actor=None, db_url=None, installation_basis=None):
    if register:
        verify_cabinet_ac_source(output, parent_run_id, ac_run_id, db_url=db_url)
    bundle = build_cabinet_arrangement_package(output, selected_block=selected_block,
        parent_run_id=parent_run_id, ac_run_id=ac_run_id, installation_basis=installation_basis)
    if register:
        persist_artifacts(run_id=ac_run_id, artifacts=[ArtifactPayload(**a) for a in bundle.artifacts],
            plugin_id=PLUGIN_ID, plugin_version=VERSION, actor=actor, db_url=db_url,
            source_ref='cabinet_arrangement_service')
        bundle.metadata['artifacts_registered'] = True
    return bundle


def restore_cabinet_arrangement(output, *, selected_block, parent_run_id, ac_run_id,
                                 db_url=None, installation_basis=None):
    verify_cabinet_ac_source(output, parent_run_id, ac_run_id, db_url=db_url)
    content, failures = load_artifact_bytes_with_failures(ac_run_id, [MANIFEST_KIND, PACKAGE_KIND],
        db_url=db_url, include_ancestors=False)
    if MANIFEST_KIND not in content:
        return None, failures
    bundle = DiagramArtifactBundle(plugin_id=PLUGIN_ID, plugin_version=VERSION, run_id=ac_run_id,
        metadata={'artifacts_registered': True},
        artifacts=[{'artifact_kind': kind, 'content': data} for kind, data in content.items()])
    selected, errors = select_cabinet_arrangement_sheet(bundle, output, selected_block=selected_block,
        parent_run_id=parent_run_id, ac_run_id=ac_run_id, installation_basis=installation_basis)
    return selected, failures + errors

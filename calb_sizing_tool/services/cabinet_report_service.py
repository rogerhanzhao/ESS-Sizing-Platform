"""Technical proposals from verified cabinet DC/AC sources and complete figure packages."""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass

from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.services.artifact_service import persist_artifacts, load_artifact_bytes_with_failures
from calb_sizing_tool.services.cabinet_document_service import cabinet_drawing_input, verify_cabinet_ac_source
from calb_sizing_tool.services.cabinet_report_data_service import build_cabinet_report_data

PLUGIN_ID = 'cabinet_technical_report_v1'
VERSION = '1.1.1'


class CabinetReportNotReady(ValueError):
    pass


@dataclass
class CabinetReportSources:
    report_data: dict
    diagram_pages: list[dict]
    fingerprint: str
    parent_run_id: str
    ac_run_id: str


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def prepare_cabinet_report(run_bundle, output, *, ac_run_id, db_url=None, installation_basis=None,
                            ac_alternative_label=None):
    from calb_sizing_tool.services.cabinet_sld_service import restore_cabinet_sld
    from calb_sizing_tool.services.cabinet_arrangement_service import restore_cabinet_arrangement
    parent = run_bundle.run_id
    verify_cabinet_ac_source(output, parent, ac_run_id, db_url=db_url)
    from calb_sizing_tool.services.ac_run_service import ac_alternative_label as saved_alternative_label
    label = saved_alternative_label(parent, ac_run_id, db_url=db_url)
    if ac_alternative_label is not None and ac_alternative_label != label:
        raise ValueError('The AC alternative label conflicts with the selected saved alternative')
    data = build_cabinet_report_data(run_bundle, output, ac_alternative_label=label)
    if installation_basis is not None:
        data['installation_basis'] = installation_basis
    blocks = sorted({g['ac_block_index'] for g in output['cabinet_group_contract']['groups']})
    sld, failures = restore_cabinet_sld(output, selected_block=blocks[0], parent_run_id=parent,
        ac_run_id=ac_run_id, db_url=db_url)
    if failures:
        raise CabinetReportNotReady('The saved SLD could not be verified: ' + '; '.join(failures))
    if sld is None:
        raise CabinetReportNotReady('Generate the cabinet SLD for this AC alternative before exporting the report.')
    arrangement, failures = restore_cabinet_arrangement(output, selected_block=blocks[0], parent_run_id=parent,
        ac_run_id=ac_run_id, db_url=db_url, installation_basis=installation_basis)
    if failures:
        raise CabinetReportNotReady('The saved arrangement could not be verified: ' + '; '.join(failures))
    if arrangement is None:
        raise CabinetReportNotReady('Generate the cabinet arrangement for this AC alternative before exporting the report.')
    sld_payloads = {a['artifact_kind']: a['content'] for a in sld.artifacts}
    layout_payloads = {a['artifact_kind']: a['content'] for a in arrangement.artifacts}
    sld_zip = sld_payloads.get('cabinet_sld_package_zip')
    layout_zip = layout_payloads.get('cabinet_arrangement_package_zip')
    if not sld_zip or not layout_zip:
        raise CabinetReportNotReady('Both complete cabinet drawing packages are required for the technical proposal.')
    pages = []
    # Both restoration services have already checked the exact child, manifest,
    # complete member set and hashes. The report always includes every AC Block.
    with zipfile.ZipFile(io.BytesIO(sld_zip)) as electrical, zipfile.ZipFile(io.BytesIO(layout_zip)) as spatial:
        for index in blocks:
            page = {'ac_block_index': index}
            for prefix, archive, stem in [('sld', electrical, f'cabinet_sld_ac_{index:03d}.concept'),
                                          ('layout', spatial, f'cabinet_arrangement_ac_{index:03d}.concept')]:
                page[prefix + '_svg'] = archive.read(stem + '.svg')
                page[prefix + '_png'] = archive.read(stem + '.png') if stem + '.png' in archive.namelist() else None
            pages.append(page)
    fingerprint = _hash(json.dumps(dict(data=data, output=cabinet_drawing_input(output), parent=parent,
        child=ac_run_id, sld_package=_hash(sld_zip), arrangement_package=_hash(layout_zip), version=VERSION),
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode())
    return CabinetReportSources(data, pages, fingerprint, parent, ac_run_id)


def _kinds(brand):
    if not re.fullmatch('[a-z0-9_]+', brand.key):
        raise ValueError('Invalid report brand key')
    return f'cabinet_report_{brand.key}_docx', f'cabinet_report_{brand.key}_manifest'


def _signature(sources, brand):
    return _hash(json.dumps(dict(source=sources.fingerprint, brand=brand.key, version=VERSION), sort_keys=True).encode())


def generate_cabinet_technical_report(run_bundle, output, *, ac_run_id, brand, actor=None, db_url=None,
                                       installation_basis=None, ac_alternative_label=None):
    from calb_sizing_tool.reporting.cabinet_report import export_cabinet_report
    from calb_sizing_tool.reporting.export_docx import make_proposal_filename
    from calb_sizing_tool.reporting.brand_profiles import neutralize_brand_text
    sources = prepare_cabinet_report(run_bundle, output, ac_run_id=ac_run_id, db_url=db_url,
        installation_basis=installation_basis, ac_alternative_label=ac_alternative_label)
    content = export_cabinet_report(sources.report_data, output, sources.diagram_pages, brand=brand)
    project = neutralize_brand_text(sources.report_data['project_name'], brand, fallback='ESS Project')
    filename = make_proposal_filename(project, version=brand.version_tag, prefix=brand.filename_prefix,
        ac_alternative=sources.report_data.get('ac_alternative_label')).removesuffix('.docx') + '_Cabinet.concept.docx'
    signature = _signature(sources, brand)
    manifest = dict(plugin_id=PLUGIN_ID, version=VERSION, document_status='concept', not_for_construction=True,
                    source_run_id=sources.parent_run_id, source_ac_run_id=ac_run_id, brand=brand.key,
                    signature=signature, content_hash=_hash(content), file_name=filename,
                    ac_block_count=len(sources.diagram_pages))
    doc_kind, manifest_kind = _kinds(brand)
    persist_artifacts(run_id=ac_run_id, plugin_id=PLUGIN_ID, plugin_version=VERSION, actor=actor, db_url=db_url,
        source_ref='cabinet_report_service', artifacts=[
            ArtifactPayload(doc_kind, filename, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            content, dict(manifest)),
            ArtifactPayload(manifest_kind, f'cabinet_report_{brand.key}.concept.json', 'application/json',
                            json.dumps(manifest, sort_keys=True, indent=2).encode(), dict(manifest))])
    return content, filename, signature


def restore_cabinet_technical_report(sources, brand, *, db_url=None):
    doc_kind, manifest_kind = _kinds(brand)
    content, failures = load_artifact_bytes_with_failures(sources.ac_run_id, [doc_kind, manifest_kind],
        db_url=db_url, include_ancestors=False)
    if failures:
        raise CabinetReportNotReady('The saved technical report could not be retrieved: ' + '; '.join(failures))
    if not content:
        return None
    try:
        manifest = json.loads(content[manifest_kind])
        if (manifest.get('plugin_id') != PLUGIN_ID
                or manifest.get('source_run_id') != sources.parent_run_id
                or manifest.get('source_ac_run_id') != sources.ac_run_id or manifest.get('brand') != brand.key):
            raise ValueError('Saved report source or brand binding mismatch')
        signature = manifest['signature']
        filename = manifest['file_name']
        if (not isinstance(signature, str) or not re.fullmatch('[a-f0-9]{64}', signature)
                or not isinstance(filename, str) or not filename.endswith('.docx')
                or '/' in filename or '\\' in filename or ':' in filename
                or not isinstance(manifest['version'], str) or not manifest['version']):
            raise ValueError('Saved report manifest is incomplete')
        data = content[doc_kind]
        if _hash(data) != manifest.get('content_hash'):
            raise ValueError('Report hash mismatch')
        # A stale, intact report can be rebuilt for changed inputs or exporter
        # versions. An unreadable or misbound artifact is never a cache miss.
        if signature != _signature(sources, brand):
            return None
        return data, filename, signature
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CabinetReportNotReady('The saved technical report is incomplete or changed. '
            'Retry the export; if the problem persists, check the saved report artifact.') from exc

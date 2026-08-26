# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

import logging
from typing import Any

import streamlit as st

_log = logging.getLogger(__name__)
from calb_sizing_tool.reporting.export_docx import (
    make_proposal_filename,
)
from calb_sizing_tool.reporting.brand_profiles import (
    BRAND_PROFILES,
    BrandAssetMissingError,
    BrandLeakError,
    neutralize_brand_text,
)
from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1
from calb_sizing_tool.runtime_paths import get_outputs_dir
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state
from calb_sizing_tool.state.workspace_state import artifact_run_id, get_workspace_context
from calb_sizing_tool.services.sld_data_source_service import AcSnapshotResolution, resolve_preferred_ac_snapshot
from calb_sizing_tool.services.artifact_service import (
    load_artifact_bytes_with_failures,
    retry_read,
)
from calb_sizing_tool.services.governed_ac_block_service import governed_poi_power_closure_issue


def _load_product_assets_for_block(block_code: str | None) -> list[dict[str, Any]]:
    if not block_code:
        return []
    try:
        from calb_sizing_tool.infra.db.models import ProductAsset
        from calb_sizing_tool.infra.db.session import session_scope
        with session_scope() as session:
            rows = (
                session.query(ProductAsset)
                .filter(
                    ProductAsset.owner_entity == "product_dc_block",
                    ProductAsset.owner_code == block_code,
                    ProductAsset.is_active.is_(True),
                )
                .order_by(ProductAsset.sort_order.asc(), ProductAsset.is_primary.desc())
                .all()
            )
            return [
                {
                    "asset_code": r.asset_code,
                    "kind": r.asset_kind,
                    "title": r.title,
                    "file_name": r.file_name,
                    "caption": r.caption,
                    "proposal_section": r.proposal_section,
                    "source_path": r.source_path,
                    "storage_uri": r.storage_uri,
                    "is_primary": r.is_primary,
                    "sort_order": r.sort_order,
                }
                for r in rows
            ]
    except Exception:
        return []


def _extract_block_identity(stage2_raw):
    block_code = None
    block_name = None
    block_table = stage2_raw.get("block_config_table") if isinstance(stage2_raw, dict) else None
    if block_table is not None and not block_table.empty:
        first_row = block_table.iloc[0]
        block_code = first_row.get("Block Code")
        block_name = first_row.get("Block Name")
    return block_code, block_name


def _extract_artifact_bytes(artifact_bundle) -> tuple[bytes | None, bytes | None]:
    """Extract (png_bytes, svg_bytes) from a DiagramArtifactBundle stored in session state.

    The bundle's .artifacts is a list[dict] with keys artifact_kind / content / file_name.
    Returns (None, None) if the bundle is absent or has no matching items.
    """
    png_bytes = svg_bytes = None
    if artifact_bundle is None:
        return png_bytes, svg_bytes
    artifact_list = getattr(artifact_bundle, "artifacts", None)
    if not isinstance(artifact_list, list):
        return png_bytes, svg_bytes
    for item in artifact_list:
        if not isinstance(item, dict):
            continue
        kind = item.get("artifact_kind", "")
        content = item.get("content")
        if not content:
            continue
        if kind.endswith("_png") and png_bytes is None:
            png_bytes = content
        elif kind.endswith("_svg") and svg_bytes is None:
            svg_bytes = content
    return png_bytes, svg_bytes


def _resolve_report_ac_snapshot(
    run_id: str | None,
    *,
    state,
    project_state: dict,
    session_state,
    db_url: str | None = None,
) -> AcSnapshotResolution:
    return resolve_preferred_ac_snapshot(
        run_id,
        project_state=project_state,
        shared_state=state,
        session_state=session_state,
        db_url=db_url,
    )


def show():
    from calb_sizing_tool.state.auth_state import get_auth_context, clear_auth_context
    _auth = get_auth_context()
    from calb_sizing_tool.ui._ui import page_header as _ph
    if _auth and _auth.is_guest:
        _ph("Report Export", "Proposal & Technical Document Export")
        st.markdown(
            """
            <div style="background:#FFF8E6;border:1px solid #F0C060;border-radius:8px;
                        padding:1.25rem 1.5rem;margin-top:1rem">
                <div style="color:#7A5500;font-weight:700;font-size:0.95rem;margin-bottom:0.4rem">
                    Export requires a registered account
                </div>
                <div style="color:#7A5500;font-size:0.82rem;line-height:1.6">
                    Guest mode allows DC / AC sizing and SLD generation.<br>
                    Report download and proposal export are available after sign-in.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Sign In to Enable Export", use_container_width=False):
            clear_auth_context()
            st.rerun()
        return

    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()
    dc_results = state.dc_results or {}
    ac_results = state.ac_results or {}
    artifacts = state.artifacts
    outputs_dir = get_outputs_dir()
    # The report resolves its AC configuration FROM the DC parent run.  This is
    # deliberately distinct from ``_active_run_id`` below: when an AC
    # alternative is selected, artifacts belong to that child run, while the
    # alternative snapshot still names the DC run in ``source_run_id``.  Passing
    # the child ID to the resolver makes its cross-run safety check reject the
    # very alternative the user selected and falsely report that AC sizing is
    # missing.
    workspace = get_workspace_context()
    _dc_run_id = workspace.get("run_id")
    # Read artifacts at the AC alternative when one is selected. The reader walks
    # up parent_run_id, so an alternative that never produced a given figure still
    # shows the DC run's — and a database written before AC runs existed is
    # unaffected.
    _active_run_id = artifact_run_id()

    # --- SLD bytes: DB artifact_registry → plugin bundle → old artifacts dict → old diagram_results → file ---
    # Reads that failed after their retries. A figure this page could not read is
    # NOT a figure the run never made, and the page must not offer "generate it"
    # as the remedy for a locked database.
    # Kept per figure: a layout that could not be read must not make the SLD
    # chip claim the SLD exists. Same rule as report_v2._read_failures_for.
    sld_read_failures: list[str] = []
    layout_read_failures: list[str] = []
    sld_png = sld_svg = None
    if _active_run_id:
        _db_sld, _sld_failures = load_artifact_bytes_with_failures(
            _active_run_id, ["sld_png", "sld_svg"]
        )
        sld_read_failures.extend(_sld_failures)
        sld_png = _db_sld.get("sld_png")
        sld_svg = _db_sld.get("sld_svg")
        if sld_png is not None:
            _log.info("SLD source: DB artifact_registry (run_id=%s)", _active_run_id)
    bundle_sld_png, bundle_sld_svg = _extract_artifact_bytes(st.session_state.get("sld_artifacts"))
    if sld_png is None:
        sld_png = bundle_sld_png
    if sld_svg is None:
        sld_svg = bundle_sld_svg
    if sld_png is not None:
        _log.info("SLD source: plugin bundle or DB artifact")
    if sld_png is None:
        sld_png = artifacts.get("sld_png_bytes")
        if sld_png is not None:
            _log.info("SLD source: artifacts dict (sld_png_bytes)")
    if sld_svg is None:
        sld_svg = artifacts.get("sld_svg_bytes")
    if sld_png is None:
        # legacy diagram_results structure (older sessions)
        diagram_results = st.session_state.get("diagram_results") or {}
        for style_key in (diagram_results.get("last_style"), "raw_v05", "pro_v10", "jp_v08"):
            entry = diagram_results.get(style_key) if style_key else None
            if isinstance(entry, dict):
                sld_png = sld_png or entry.get("png")
                sld_svg = sld_svg or entry.get("svg")
                if sld_png:
                    _log.info("SLD source: legacy diagram_results[%s]", style_key)
                    break
    if sld_png is None:
        candidate = outputs_dir / "sld_latest.png"
        if candidate.exists():
            sld_png, _err = retry_read(candidate.read_bytes)
            if _err is not None:
                sld_read_failures.append(f"{candidate.name} could not be read ({_err})")
            else:
                _log.info("SLD source: filesystem (%s)", candidate)
    if sld_svg is None:
        candidate = outputs_dir / "sld_latest.svg"
        if candidate.exists():
            sld_svg, _err = retry_read(candidate.read_bytes)
            if _err is not None:
                sld_read_failures.append(f"{candidate.name} could not be read ({_err})")
    if sld_png is None:
        _log.warning("SLD: no image resolved from any source")

    # --- Layout bytes: same DB-first priority chain ---
    layout_png = layout_svg = None
    if _active_run_id:
        _db_layout, _layout_failures = load_artifact_bytes_with_failures(
            _active_run_id, ["layout_png", "layout_svg"]
        )
        layout_read_failures.extend(_layout_failures)
        layout_png = _db_layout.get("layout_png")
        layout_svg = _db_layout.get("layout_svg")
        if layout_png is not None:
            _log.info("Layout source: DB artifact_registry (run_id=%s)", _active_run_id)
    bundle_layout_png, bundle_layout_svg = _extract_artifact_bytes(st.session_state.get("layout_artifacts"))
    if layout_png is None:
        layout_png = bundle_layout_png
    if layout_svg is None:
        layout_svg = bundle_layout_svg
    if layout_png is not None:
        _log.info("Layout source: plugin bundle or DB artifact")
    if layout_png is None:
        layout_png = artifacts.get("layout_png_bytes") or st.session_state.get("layout_png_bytes")
        if layout_png is not None:
            _log.info("Layout source: artifacts dict (layout_png_bytes)")
    if layout_svg is None:
        layout_svg = artifacts.get("layout_svg_bytes") or st.session_state.get("layout_svg_bytes")
    if layout_png is None:
        layout_results = st.session_state.get("layout_results") or {}
        for style_key in (layout_results.get("last_style"), "raw_v05"):
            entry = layout_results.get(style_key) if style_key else None
            if isinstance(entry, dict):
                layout_png = layout_png or entry.get("png")
                layout_svg = layout_svg or entry.get("svg")
                if layout_png:
                    _log.info("Layout source: legacy layout_results[%s]", style_key)
                    break
    if layout_png is None:
        candidate = outputs_dir / "layout_latest.png"
        if candidate.exists():
            layout_png = candidate.read_bytes()
            _log.info("Layout source: filesystem (%s)", candidate)
    if layout_svg is None:
        candidate = outputs_dir / "layout_latest.svg"
        if candidate.exists():
            layout_svg = candidate.read_bytes()
    if layout_png is None:
        _log.warning("Layout: no image resolved from any source")

    # Write resolved bytes back into the artifacts dict so build_report_context() picks them up
    if sld_png:
        artifacts["sld_png_bytes"] = sld_png
    if sld_svg:
        artifacts["sld_svg_bytes"] = sld_svg
    if layout_png:
        artifacts["layout_png_bytes"] = layout_png
    if layout_svg:
        artifacts["layout_svg_bytes"] = layout_svg

    _ph("Report Export", "Proposal & Technical Document Export")

    stage13_output = (
        dc_results.get("stage13_output")
        or st.session_state.get("stage13_output")
        or {}
    )
    ac_resolution = _resolve_report_ac_snapshot(
        _dc_run_id,
        state=state,
        project_state=project_state,
        session_state=st.session_state,
    )
    ac_output = dict(ac_resolution.snapshot.output) if ac_resolution.snapshot is not None else {}
    if ac_output:
        st.session_state["ac_output"] = ac_output
        if isinstance(ac_results, dict):
            ac_results.update(ac_output)
        if isinstance(ac_resolution.snapshot.inputs, dict) and ac_resolution.snapshot.inputs:
            ac_inputs = st.session_state.get("ac_inputs")
            if isinstance(ac_inputs, dict):
                ac_inputs.update(ac_resolution.snapshot.inputs)

    if not stage13_output or not ac_output:
        st.warning("Run DC sizing and AC sizing first to enable report export.")
        if stage13_output and not ac_output:
            st.info(
                "DC results found but AC sizing is missing. "
                "Run AC Sizing on this project/case, or restore a run that includes AC results."
            )
        return

    power_closure_issue = governed_poi_power_closure_issue(ac_output)
    if power_closure_issue:
        st.error(f"Report export blocked: {power_closure_issue}")
        return

    # Brand is an export boundary, not a late cover-page decoration. Select it
    # before resolving customer-visible defaults or building ReportContext.
    report_template = st.selectbox(
        "Report Template",
        list(BRAND_PROFILES.keys()),
        index=0,
        key="report_template_brand",
    )
    brand = BRAND_PROFILES[report_template]

    project_name = None
    project = st.session_state.get("project")
    if isinstance(project, dict):
        project_name = project.get("name")
    project_name = (
        project_name
        or st.session_state.get("project_name")
        or stage13_output.get("project_name")
        or ac_output.get("project_name")
        or "Untitled ESS Project"
    )
    st.session_state["project_name"] = project_name

    grid_kv = (
        ac_output.get("grid_kv")
        or ac_output.get("mv_kv")
        or stage13_output.get("poi_nominal_voltage_kv")
    )
    pcs_lv_v = (
        ac_output.get("inverter_lv_v")
        or ac_output.get("lv_voltage_v")
        or ac_output.get("lv_v")
    )
    inputs = {
        "Project Name": project_name,
        "POI Power Requirement (MW)": ac_output.get("poi_power_mw"),
        "POI Energy Requirement (MWh)": ac_output.get("poi_energy_mwh"),
        "Grid Voltage (kV)": grid_kv,
        "PCS AC Output Voltage (V_LL,rms)": pcs_lv_v,
        "Standard AC Block Size (MW)": ac_output.get("block_size_mw"),
    }

    report_context = {
        "project_name": project_name,
        "inputs": inputs,
        "tool_version": "V1.0",
        "sld_png_bytes": sld_png,
        "sld_svg_bytes": sld_svg,
        "layout_png_bytes": layout_png,
        "layout_svg_bytes": layout_svg,
    }

    st.markdown("#### Report Content")
    st.subheader("Report Content Preview")
    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.success("✓  DC Sizing")
    rc2.success("✓  AC Sizing")
    if sld_png or sld_svg:
        rc3.success("✓  SLD Image")
    elif sld_read_failures:
        rc3.warning("!  SLD (exists, could not be read)")
    else:
        rc3.info("○  SLD (not generated)")
    if layout_png or layout_svg:
        rc4.success("✓  Typical AC Block Arrangement (Concept Only)")
    elif layout_read_failures:
        rc4.warning("!  Layout (exists, could not be read)")
    else:
        rc4.info("○  Layout (not generated)")
    read_failures = sld_read_failures + layout_read_failures
    if read_failures:
        st.warning(
            "A stored figure could not be read after retrying. It has NOT been lost — "
            "regenerating is not the fix. Retry the export, and if it persists check "
            "the outputs directory and the run registry:\n\n"
            + "\n".join(f"- {message}" for message in read_failures[:5])
        )

    st.divider()

    # --- Database Provenance Panel ---
    active_run_id = workspace.get("run_id")
    active_project_code = workspace.get("project_code")
    active_case_code = workspace.get("case_code")
    active_case_name = workspace.get("case_name")
    active_project_name = workspace.get("project_name")

    with st.expander("Database Provenance", expanded=True):
        p1, p2 = st.columns(2)
        with p1:
            st.caption("Project")
            st.write(active_project_name or project_name)
            st.caption("Project Code")
            st.write(active_project_code or "—")
        with p2:
            st.caption("Case")
            st.write(active_case_name or "—")
            st.caption("Case Code")
            st.write(active_case_code or "—")

        if active_run_id:
            st.success(f"DC Run ID: `{active_run_id}`  — linked to database")
            # Block library source provenance
            _block_src_label = st.session_state.get("dc_block_source") or "Excel reference library"
            if "Admin" in _block_src_label:
                st.info("DC Block Library: **Admin product library** (Phase B DB)")
            else:
                st.info("DC Block Library: Excel reference library")
            # Show AC snapshot linkage
            _ac_run_id = ac_output.get("source_ac_run_id") if ac_output else None
            if _ac_run_id:
                st.success(f"AC Run ID: `{_ac_run_id}`  — AC sizing persisted")
            elif ac_output:
                st.info("AC results loaded from snapshot attached to DC run (fully traceable).")
            else:
                st.warning("AC sizing not yet performed for this run.")
        else:
            st.warning(
                "No database run linked. Run DC Sizing and persist the run first. "
                "The report will be generated from the current session only and will "
                "carry a provenance warning."
            )

    # --- Standard Product Information (from ProductAsset DB) ---
    _stage2_raw_preview = stage13_output.get("stage2_raw", {})
    _preview_block_code, _preview_block_name = _extract_block_identity(_stage2_raw_preview)
    _dc_block_src = st.session_state.get("dc_block_source", "Excel reference library")
    _product_assets = _load_product_assets_for_block(_preview_block_code)

    with st.expander("Standard Product Information", expanded=bool(_product_assets)):
        if _preview_block_code:
            st.caption(f"DC Block: **{_preview_block_code}**" + (f" — {_preview_block_name}" if _preview_block_name else ""))
        if not _product_assets:
            st.info(
                "No product assets registered for this DC block. "
                "Add datasheets and product images in ⚙ Product & Database → Product Assets."
            )
        else:
            _kind_order = ["datasheet", "product_image", "proposal_image", "source_file", "other"]
            _by_kind: dict[str, list] = {}
            for _a in _product_assets:
                _by_kind.setdefault(_a["kind"], []).append(_a)
            for _kind in _kind_order:
                if _kind not in _by_kind:
                    continue
                st.markdown(f"**{_kind.replace('_', ' ').title()}**")
                for _asset in _by_kind[_kind]:
                    _ref = _asset.get("storage_uri") or _asset.get("source_path") or ""
                    _badge = " ⭐" if _asset["is_primary"] else ""
                    _section = f"  ·  *{_asset['proposal_section']}*" if _asset.get("proposal_section") else ""
                    st.markdown(
                        f"- `{_asset['asset_code']}`{_badge}  {_asset['title']}{_section}"
                        + (f"  —  `{_asset['file_name']}`" if _asset.get("file_name") else "")
                        + (f"\n  > {_asset['caption']}" if _asset.get("caption") else "")
                    )
                    if _ref:
                        st.caption(f"  Ref: {_ref}")

    st.divider()

    st.subheader("Downloads")

    st.info("AC Report generation moved to V2.2 format only.")

    with st.container(border=True):
        stage2_raw = stage13_output.get("stage2_raw", {})
        block_code, block_name = _extract_block_identity(stage2_raw)

        # Build comprehensive project inputs from stage13_output
        project_inputs_for_report = {
            "project_name": project_name,
            "poi_power_mw": stage13_output.get("poi_power_req_mw"),
            "poi_energy_mwh": stage13_output.get("poi_energy_req_mwh"),
            "poi_energy_guarantee_mwh": stage13_output.get("poi_energy_req_mwh"),
            "poi_guarantee_year": stage13_output.get("poi_guarantee_year"),
            "poi_frequency_hz": stage13_output.get("poi_frequency_hz"),
        }
        ctx = build_report_context(
            session_state=st.session_state,
            stage_outputs={
                "stage13_output": stage13_output,
                "stage2": stage13_output.get("stage2_raw", {}),
                "ac_output": ac_output,
                "sld_snapshot": st.session_state.get("sld_snapshot"),
            },
            project_inputs=project_inputs_for_report,
            scenario_ids=stage13_output.get("selected_scenario", "container_only"),
        )
        # Confirm the figures were RETRIEVED before building anything.
        #
        # Owner ruling 2026-08-08: reaching this page means the drawing was
        # generated and confirmed on its own page already. So a figure the
        # registry HAS but this process could not read is a retrieval problem,
        # never a missing drawing — and a proposal that silently omits a
        # confirmed drawing is worse than no proposal. Fail closed: the reads
        # were already retried (artifact_service.retry_read); what survived
        # that stops the export instead of shaping the document.
        #
        # A figure that was genuinely never generated does NOT stop anything —
        # that is the "not generated" note in sections 7/8, unchanged.
        blocking_failures = sld_read_failures + layout_read_failures + [
            message
            for message in ctx.artifact_read_failures
            if message not in sld_read_failures and message not in layout_read_failures
        ]
        if blocking_failures:
            st.error(
                "**Report not generated — a figure this run HAS could not be retrieved.**\n\n"
                "This is not a missing drawing: the run recorded it, and it was "
                "confirmed on its own page before you got here. The read was already "
                "retried automatically. Generating now would ship a proposal with a "
                "confirmed drawing silently absent, so the export stops here.\n\n"
                + "\n".join(f"- {message}" for message in blocking_failures[:5])
            )
            st.caption(
                "Retry below. If it keeps failing, the stored figure needs attention "
                "(outputs directory or run registry) — regenerating the drawing is not the fix."
            )
            st.button("Retry retrieving the figures", key="report_retry_artifact_fetch")
            return

        try:
            comb_bytes = export_report_v2_1(ctx, brand=brand)
        except (BrandAssetMissingError, BrandLeakError) as exc:
            # Never fall back to another brand's assets or unverified raster
            # drawings in a white-label report.
            st.error(str(exc))
        else:
            # Naming the alternative keeps two AC branches of one DC run from
            # downloading as the same file. ctx.ac_alternative_label is None when
            # there is only one, so the ordinary report name is unchanged.
            proposal_project_name = neutralize_brand_text(
                project_name, brand, fallback="Untitled ESS Project"
            )
            proposal_filename = make_proposal_filename(
                proposal_project_name,
                version=brand.version_tag,
                prefix=brand.filename_prefix,
                ac_alternative=ctx.ac_alternative_label,
            )
            st.download_button(
                f"Download Combined Report {brand.display_name}",
                comb_bytes,
                proposal_filename,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
            )

    if not sld_png and not sld_svg:
        st.info("SLD image not found. Generate it in Single Line Diagram.")
    if not layout_png and not layout_svg:
        st.info("Typical AC Block Arrangement image not found. Generate it from the corresponding concept page.")



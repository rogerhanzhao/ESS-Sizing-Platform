"""The cabinet branch keeps the existing direct report download interaction.

Real Streamlit rendering is exercised with already verified source data. The
document and artifact boundaries are replaced so these tests never render a
drawing, query a database, or write an export.
"""
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_cabinet_report_data import saved_cabinet
from calb_sizing_tool.reporting.brand_profiles import CALB_BRAND, GUOXIA_BRAND
from calb_sizing_tool.services.cabinet_report_data_service import build_cabinet_report_data


def _report_page():
    import streamlit as st
    from types import SimpleNamespace
    from calb_sizing_tool.ui.cabinet_report_view import show_cabinet_report

    show_cabinet_report(
        st.session_state["test_ac_output"], parent_run_id="saved-dc",
        workspace={"project_name": "Saved project", "case_name": "Saved case", "ac_run_id": "saved-ac"},
        auth_user=SimpleNamespace(username="reviewer"), authoritative=True,
    )


@pytest.fixture
def report_ui(saved_cabinet, monkeypatch):
    from calb_sizing_tool.ui import cabinet_report_view as view
    from calb_sizing_tool.ui import report_export_view as shared_report
    from calb_sizing_tool.services import ac_run_service

    dc_bundle, output = saved_cabinet
    data = build_cabinet_report_data(dc_bundle, output)
    sources = SimpleNamespace(report_data=data, diagram_pages=[{"ac_block_index": 1}, {"ac_block_index": 2}])
    calls = {"prepare": [], "restore": [], "generate": [], "assets": []}
    behavior = {"prepared_error": None, "restore_error": None, "cached_report": None}
    report = (b"PK mocked report document", "CALB_Cabinet.concept.docx", "verified-signature")

    def prepare(*args, **kwargs):
        calls["prepare"].append((args, kwargs))
        if behavior["prepared_error"]:
            raise behavior["prepared_error"]
        return sources

    def restore(*args, **kwargs):
        calls["restore"].append((args, kwargs))
        if behavior["restore_error"]:
            raise behavior["restore_error"]
        return behavior["cached_report"]

    def generate(*args, **kwargs):
        calls["generate"].append((args, kwargs))
        return report

    def assets(block_code):
        calls["assets"].append(block_code)
        return []

    monkeypatch.setattr(view, "cabinet_document_context", lambda *args, **kwargs: ("saved-ac", dc_bundle))
    monkeypatch.setattr(ac_run_service, "ac_alternative_label", lambda *args, **kwargs: "A")
    monkeypatch.setattr(view, "prepare_cabinet_report", prepare)
    monkeypatch.setattr(view, "restore_cabinet_technical_report", restore)
    monkeypatch.setattr(view, "generate_cabinet_technical_report", generate)
    monkeypatch.setattr(shared_report, "_load_product_assets_for_block", assets)

    def open_page():
        page = AppTest.from_function(_report_page, default_timeout=30)
        page.session_state["test_ac_output"] = output
        return page.run()

    return SimpleNamespace(open=open_page, calls=calls, behavior=behavior, report=report)


def _main_download(page, brand=CALB_BRAND):
    label = "Download Technical Proposal"
    downloads = [button for button in page.get("download_button") if button.label == label]
    assert len(downloads) == 1
    assert downloads[0].proto.type == "primary"
    assert downloads[0].proto.ignore_rerun is True
    return downloads[0]


def test_ready_saved_sources_offer_direct_download_without_a_generate_step(report_ui):
    page = report_ui.open()
    assert not page.exception
    _main_download(page)
    assert not any("Generate" in button.label for button in page.button)
    assert len(report_ui.calls["prepare"]) == len(report_ui.calls["restore"]) == 1
    assert len(report_ui.calls["generate"]) == 1
    assert report_ui.calls["generate"][0][1]["brand"] is CALB_BRAND
    assert report_ui.calls["generate"][0][1]["ac_run_id"] == "saved-ac"

    headings = {element.value for element in page.subheader}
    assert {"Selected Run Summary", "Report Content", "Downloads"}.issubset(headings)
    expanders = {element.label for element in page.expander}
    assert "Run references and data sources" in expanders
    assert "Standard Product Information" in expanders
    statuses = " ".join(element.value for element in page.success)
    assert "DC Sizing" in statuses and "AC Sizing" in statuses and "SLD" in statuses
    assert "Arrangement" in statuses
    assert report_ui.calls["assets"] == ["CALB_0.418MWh_CAB_8P"]


def test_verified_cached_report_download_does_not_generate_another_export(report_ui):
    report_ui.behavior["cached_report"] = report_ui.report
    page = report_ui.open()
    assert not page.exception
    _main_download(page)
    assert len(report_ui.calls["restore"]) == 1
    assert not report_ui.calls["generate"]
    assert not any("Generate" in button.label for button in page.button)


def test_missing_or_unverified_source_figures_do_not_build_a_report(report_ui):
    from calb_sizing_tool.services.cabinet_report_service import CabinetReportNotReady

    report_ui.behavior["prepared_error"] = CabinetReportNotReady("The saved arrangement could not be verified.")
    page = report_ui.open()
    assert not page.exception
    assert not page.get("download_button")
    assert not report_ui.calls["restore"] and not report_ui.calls["generate"]
    labels = {button.label for button in page.button}
    assert "Retry retrieving the figures" in labels
    assert any("Single Line Diagram" in label for label in labels)
    assert any("Typical AC Block Arrangement" in label for label in labels)


@pytest.mark.parametrize("error", [RuntimeError("Storage unavailable"), ValueError("Saved report signature mismatch")])
def test_report_cache_read_failure_requires_retry_without_regeneration(report_ui, error):
    report_ui.behavior["restore_error"] = error
    page = report_ui.open()
    assert not page.exception
    assert not page.get("download_button")
    assert not report_ui.calls["generate"]
    assert any(button.label == "Retry retrieving the report" for button in page.button)
    # A transient storage problem can be retried without sending the user
    # through a separate report generation action or altering the figures.
    report_ui.behavior["restore_error"] = None
    report_ui.behavior["cached_report"] = report_ui.report
    next(button for button in page.button if button.label == "Retry retrieving the report").click()
    page = page.run()
    assert not page.exception
    _main_download(page)
    assert not report_ui.calls["generate"]


def test_shared_template_selection_passes_the_selected_white_label_profile(report_ui):
    page = report_ui.open()
    assert not page.exception
    template = next(item for item in page.selectbox if item.key == "report_template_brand")
    template.select(GUOXIA_BRAND.display_name)
    page = page.run()
    assert not page.exception
    _main_download(page, GUOXIA_BRAND)
    assert report_ui.calls["generate"][-1][1]["brand"] is GUOXIA_BRAND
    arguments, keywords = report_ui.calls["restore"][-1]
    assert keywords.get("brand", arguments[1] if len(arguments) > 1 else None) is GUOXIA_BRAND

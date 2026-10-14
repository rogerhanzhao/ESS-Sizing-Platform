import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.ui import admin_portal_view as portal


@pytest.fixture
def asset_store(tmp_path, monkeypatch):
    store = tmp_path / "outputs" / "product_assets"
    store.mkdir(parents=True)
    monkeypatch.setattr(portal, "_ASSET_STORE", store)
    return store


def test_reference_record_does_not_pretend_to_be_an_upload(asset_store):
    asset = {"source_path": "New Microsoft PowerPoint Presentation.pptx", "file_name": None}
    assert portal._managed_asset_path(asset) is None
    assert portal._asset_attachment_status(asset) == "Not uploaded"


def test_registered_upload_can_be_downloaded_in_ui(asset_store, monkeypatch):
    file = asset_store / "datasheet.pdf"
    file.write_bytes(b"%PDF-1.4 test attachment")
    asset = dict(product_asset_id="test", title="Datasheet", asset_code="TEST", source_path=str(file), file_name=file.name)
    assert portal._asset_attachment_status(asset) == "Uploaded"
    offered = []
    original = portal.st.download_button
    def capture(label, data, **kwargs):
        offered.append((data, kwargs["file_name"]))
        return original(label, data, **kwargs)
    monkeypatch.setattr(portal.st, "download_button", capture)
    app = AppTest.from_string(
        "from calb_sizing_tool.ui.admin_portal_view import _render_asset_download\n"
        f"_render_asset_download([{asset!r}])"
    ).run()
    assert not app.exception
    assert offered == [(file.read_bytes(), "datasheet.pdf")]
    assert any(button.label == "Download selected attachment" for button in app.get("download_button"))


def test_download_rejects_paths_outside_asset_store(asset_store, tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("private")
    for path in [str(secret), str(asset_store / ".." / ".." / ".." / "outside.txt")]:
        asset = {"source_path": path, "file_name": "outside.txt"}
        assert portal._managed_asset_path(asset) is None
        assert portal._asset_attachment_status(asset) == "File unavailable"


def test_download_handles_missing_file_without_crash(asset_store):
    asset = dict(product_asset_id="test", title="Missing", asset_code="TEST", source_path=str(asset_store / "gone.pdf"), file_name="gone.pdf")
    app = AppTest.from_string(
        "from calb_sizing_tool.ui.admin_portal_view import _render_asset_download\n"
        f"_render_asset_download([{asset!r}])"
    ).run()
    assert not app.exception
    assert app.warning
    assert not app.get("download_button")

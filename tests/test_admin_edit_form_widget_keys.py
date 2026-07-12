from streamlit.testing.v1 import AppTest


def _cells_page_like_app() -> None:
    """Reproduce the Cells page abort: an edit form whose widget labels and
    values coincide with the add form rendered on the same page.

    Before the fix the edit-form widgets had no explicit keys, so Streamlit
    derived identical widget IDs for both forms and raised
    DuplicateWidgetID, aborting the page render.
    """
    import streamlit as st

    from calb_sizing_tool.ui import admin_portal_view

    class _StubService:
        def update_record(self, entity, record_id, values):
            return True

    record = {
        "id": "cell-1",
        "model_code": "",           # empty text matches the add form default ""
        "manufacturer": "",
        "capacity_ah": 0.0,
        "is_active": True,           # matches add-form "Active" default
        "is_published": False,       # matches add-form "Published" default
    }
    # The add form, exactly like the real Cells page renders it.
    with st.form("admin_add_product_cell"):
        st.text_input("Model Code", value="")
        st.text_input("Manufacturer", value="")
        st.number_input("Capacity Ah", value=0.0, step=1.0)
        c1, c2 = st.columns(2)
        c1.checkbox("Active", value=True)
        c2.checkbox("Published", value=False)
        st.form_submit_button("Add")

    admin_portal_view._render_edit_form(
        service=_StubService(),
        title="Cell",
        entity="product_cell",
        items=[record],
        id_field="id",
        label_fields=["model_code", "manufacturer"],
        specs=[
            {"key": "model_code", "label": "Model Code", "kind": "text"},
            {"key": "manufacturer", "label": "Manufacturer", "kind": "text"},
            {"key": "capacity_ah", "label": "Capacity Ah", "kind": "float"},
        ],
    )


def test_edit_form_widgets_do_not_collide_with_add_form():
    app = AppTest.from_function(_cells_page_like_app, default_timeout=10)
    app.run()

    assert not app.exception
    # Both forms must be fully rendered: 2x Model Code / Manufacturer inputs,
    # 2x Capacity, 4 checkboxes (Active/Published in each form).
    assert len(app.text_input) == 4
    assert len(app.number_input) == 2
    assert len(app.checkbox) == 4

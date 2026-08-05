from streamlit.testing.v1 import AppTest


def _first_project_onboarding_app() -> None:
    from calb_sizing_tool.services.auth_service import AuthUser
    from calb_sizing_tool.ui import workbench_view

    workbench_view._render_workbench_css()
    workbench_view._render_first_project_onboarding(
        AuthUser(
            user_id="test-user",
            username="test-user",
            display_name="Test User",
            roles=["normal_user"],
        )
    )


def _empty_workbench_app() -> None:
    import streamlit as st

    from calb_sizing_tool.ui import workbench_view

    st.session_state["auth_context"] = {
        "user_id": "test-user",
        "username": "test-user",
        "display_name": "Test User",
        "roles": ["normal_user"],
    }
    workbench_view._load_projects = lambda _auth_user: []
    workbench_view.show()


def _run_registry_app() -> None:
    from calb_sizing_tool.ui import workbench_view

    workbench_view._render_workbench_css()
    workbench_view._render_run_registry(
        [
            {
                "sizing_run_id": "run-1",
                "created_at": "2026-07-14 00:00",
                "scenario_id": "container_only",
                "poi_power_req_mw": 100.0,
                "poi_energy_req_mwh": 400.0,
                "converged": True,
            }
        ],
        {"case_id": "case-1", "run_id": "run-1"},
        auth_user=None,
    )


def _duplicate_case_form_app() -> None:
    from calb_sizing_tool.services.auth_service import AuthUser
    from calb_sizing_tool.ui import workbench_view

    workbench_view._render_create_case_form(
        {
            "project_id": "project-1",
            "project_code": "project-1",
            "project_name": "Project 1",
        },
        AuthUser(
            user_id="test-user",
            username="test-user",
            display_name="Test User",
            roles=["normal_user"],
        ),
        form_key="duplicate_case_form",
    )


def test_first_project_onboarding_focuses_on_the_next_action():
    app = AppTest.from_function(_first_project_onboarding_app, default_timeout=10)
    app.run()

    assert not app.exception
    assert [item.value for item in app.subheader] == ["Create your first project"]
    assert [item.label for item in app.text_input] == ["Project Name"]
    assert [item.label for item in app.text_area] == ["Description (optional)"]
    assert [item.label for item in app.button] == ["Create Project"]
    assert len(app.info) == 0
    assert len(app.dataframe) == 0


def test_empty_workbench_hides_deferred_case_and_run_panels():
    app = AppTest.from_function(_empty_workbench_app, default_timeout=10)
    app.run()

    assert not app.exception
    assert [item.value for item in app.subheader] == ["Create your first project"]
    assert [item.label for item in app.text_input] == ["Project Name"]
    assert [item.label for item in app.button] == ["DC Sizing", "AC Sizing", "SLD", "Report Export", "Create Project"]
    assert len(app.info) == 0
    assert len(app.dataframe) == 0


def test_run_registry_avoids_streamlit_arrow_dataframe_serialisation():
    app = AppTest.from_function(_run_registry_app, default_timeout=10)
    app.run()

    assert not app.exception
    assert len(app.dataframe) == 0
    assert [item.label for item in app.selectbox] == ["Restore run"]
    assert any("wb-run-table" in item.value for item in app.markdown)


def test_duplicate_case_is_rejected_without_a_technical_exception(monkeypatch):
    from contextlib import contextmanager

    from calb_sizing_tool.ui import workbench_view

    observed_case_codes = []
    observed_project_ids = []

    @contextmanager
    def fake_session_scope():
        yield object()

    class ExistingCaseRepository:
        def __init__(self, _session):
            pass

        def get_case_by_code(self, case_code, project_id=None):
            # Identity is (project_id, case_code): the view must scope its
            # duplicate check, or one project's code would block another's.
            observed_project_ids.append(project_id)
            observed_case_codes.append(case_code)
            return object()

        def create_case(self, **_kwargs):
            raise AssertionError("Duplicate case must not be persisted")

    class AllowProjectAccess:
        def __init__(self, _session, _auth_user):
            pass

        def ensure_project_access(self, _project_id):
            return None

    monkeypatch.setattr(workbench_view, "session_scope", fake_session_scope)
    monkeypatch.setattr(workbench_view, "CaseRepository", ExistingCaseRepository)
    monkeypatch.setattr(workbench_view, "AccessControlService", AllowProjectAccess)

    app = AppTest.from_function(_duplicate_case_form_app, default_timeout=10)
    app.run()
    app.text_input[0].set_value("Existing Case")
    app.button[0].click()
    app.run()

    # A Case is 方案 x scenario, so the scenario belongs in the code.
    assert observed_case_codes == ["project-1-existing-case-container-only"]
    assert observed_project_ids == ["project-1"]
    assert not app.exception
    assert [item.value for item in app.error] == [
        "A case with the same name already exists in this project."
    ]

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

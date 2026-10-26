"""The bounded tail preview must not change the original sizing request or flow."""
from __future__ import annotations

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from tests.test_dc_page_run_smoke import signed_in_workspace, _run_sizing, _dc_run_id, _app


def test_original_form_has_one_collapsed_tail_preview_and_one_run(signed_in_workspace):
    app = signed_in_workspace()
    assert not app.exception
    expander = next(item for item in app.expander if item.label == 'Advanced: Reduced-string tail')
    assert expander.proto.expanded is False
    option = app.radio(key='dc_tail_option_preview')
    assert option.options == ['Standard 12-string only']
    assert option.value == 'Standard 12-string only'
    assert option.disabled
    assert len([item for item in app.button if item.label == 'Run Sizing']) == 1
    assert any(item.label == 'Advanced: Efficiency Chain' for item in app.expander)


def test_stale_tail_preview_cannot_change_saved_standard_run(signed_in_workspace):
    opened = signed_in_workspace()
    # A stale session is encountered before widgets are rebuilt. Injecting an
    # unavailable radio value into an existing AppTest tree fails in its driver
    # before the application's reset code can run.
    app = _app()
    for key in ('auth_context', 'active_project_id', 'active_project_name',
                'active_case_id', 'active_case_name'):
        app.session_state[key] = opened.session_state[key]
    app.session_state['main_nav'] = 'DC Sizing'
    app.session_state['dc_tail_option_preview'] = 'Allow one 10-string tail'
    app = app.run()
    assert app.radio(key='dc_tail_option_preview').value == 'Standard 12-string only'
    sized = _run_sizing(app)
    assert not sized.exception
    assert any(button.label == 'AC Sizing →' for button in sized.button)
    with session_scope() as session:
        repo = RunRepository(session)
        inputs = repo.get_input_snapshots(_dc_run_id(sized))[-1].snapshot_json
        outputs = repo.get_output_snapshots(_dc_run_id(sized))[-1].snapshot_json
    assert outputs['stage2']['mode'] == 'container_only'
    assert len(outputs['stage2']['block_config_items']) == 1
    assert not any('tail' in key for key in inputs['case_input'])


def test_tail_maintenance_read_failure_keeps_standard_form(signed_in_workspace, monkeypatch):
    from calb_sizing_tool.services.product_admin_service import ProductAdminService
    def unavailable(self, snapshot=None):
        raise ValueError('Synthetic read failure')
    monkeypatch.setattr(ProductAdminService, 'dc_block_maintenance_rows', unavailable)
    app = signed_in_workspace()
    assert not app.exception
    assert any('Product maintenance could not be read' in item.value for item in app.caption)
    assert any(item.label == 'Run Sizing' and not item.disabled for item in app.button)

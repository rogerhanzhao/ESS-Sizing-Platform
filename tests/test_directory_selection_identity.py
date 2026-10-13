from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest


def _directory_app(page):
    from calb_sizing_tool.ui import projects_view, cases_view
    (projects_view if page == 'project' else cases_view).show()


@pytest.mark.parametrize('page', ['project', 'case'])
def test_second_same_name_record_opens_by_identity(monkeypatch, page):
    from calb_sizing_tool.ui import projects_view, cases_view
    module = projects_view if page == 'project' else cases_view
    records = [SimpleNamespace(project_id=f'p{i}', project_name='Same name',
                project_code=f'project-{i}', created_at=None,
                sizing_case_id=f'c{i}', case_name='Same name', case_code=f'case-{i}',
                scenario_mode='container_only') for i in (1, 2)]

    @contextmanager
    def session():
        yield object()

    access = SimpleNamespace(list_projects=lambda: records,
                             list_cases_by_project=lambda _: records)
    selected = []
    monkeypatch.setattr(module, 'session_scope', session)
    monkeypatch.setattr(module, 'AccessControlService', lambda *args: access)
    monkeypatch.setattr(module, 'get_auth_context', lambda: object())
    monkeypatch.setattr(module, 'get_auth_user', lambda: object())
    monkeypatch.setattr(module, 'navigate_now', lambda _: None)
    if page == 'project':
        monkeypatch.setattr(module, 'set_active_project', lambda **kw: selected.append(kw))
    else:
        monkeypatch.setattr(module, 'get_workspace_context', lambda: dict(project_id='p1', case_id='c1'))
        monkeypatch.setattr(module, 'set_active_case', lambda **kw: selected.append(kw))
    app = AppTest.from_function(_directory_app, args=(page,)).run()
    assert not app.exception
    assert len(set(app.selectbox[0].options)) == 2
    app.selectbox[0].select('p2' if page == 'project' else 'c2').run()
    next(b for b in app.button if b.label == ('Open Project' if page == 'project' else 'Open Case')).click().run()
    assert not app.exception
    assert selected[-1]['project_id' if page == 'project' else 'case_id'] == ('p2' if page == 'project' else 'c2')


def test_history_number_display_preserves_zero_and_does_not_mutate_values():
    from calb_sizing_tool.ui.run_history_view import _display_number
    value = 91.44401276085988
    assert _display_number(value) == '91.444'
    assert value == 91.44401276085988
    assert _display_number(0) == '0.000'
    assert _display_number(None) == '—'

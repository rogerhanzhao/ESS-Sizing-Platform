from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('calb_backup', ROOT / 'deploy/docker/calb_backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.delenv('CALB_DATABASE_URL', raising=False)
    root = tmp_path / 'runtime'
    (root / 'state').mkdir(parents=True)
    (root / 'outputs').mkdir()
    (root / 'outputs/figure.svg').write_bytes(b'<svg/>')
    with sqlite3.connect(root / 'state/calb_sizing.sqlite') as db:
        db.execute('pragma journal_mode=WAL')
        db.execute('create table artifact_registry(file_path text, content_hash text)')
        db.execute('insert into artifact_registry values (?, ?)', ('figure.svg', hashlib.sha256(b'<svg/>').hexdigest()))
    config = tmp_path / 'deploy.env'
    config.write_text('PRIVATE_TEST_CONFIG=example')
    return root, config


def test_backup_restores_database_and_checks_every_file(runtime):
    root, config = runtime
    archive = backup.create_backup(root, config)
    result = backup.verify_archive(archive)
    assert result['database_integrity'] == 'ok'
    assert result['files'] == 3
    with tarfile.open(archive) as tar:
        assert tar.extractfile('outputs/figure.svg').read() == b'<svg/>'
        assert tar.extractfile('config/deploy.env').read() == config.read_bytes()


def test_backup_does_not_publish_an_incomplete_recovery_point(runtime):
    root, config = runtime
    (root / 'outputs/figure.svg').unlink()
    with pytest.raises(ValueError, match='Registered output missing'):
        backup.create_backup(root, config)
    assert not list((root / 'backups').glob('*.tar.gz'))


def test_backup_detects_changed_artifact_and_retains_manual_archive(runtime):
    root, config = runtime
    manual = backup.create_backup(root, config)
    backup.create_backup(root, config, label='scheduled', keep=1)
    backup.create_backup(root, config, label='scheduled', keep=1)
    assert manual.exists()
    assert len(list((root / 'backups').glob('scheduled-*.tar.gz'))) == 1
    (root / 'outputs/figure.svg').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Registered output changed'):
        backup.create_backup(root, config)


def test_cleanup_protects_running_and_rollback_image_ids():
    bash = shutil.which('bash') or 'C:/Program Files/Git/bin/bash.exe'
    if not Path(bash).exists():
        pytest.skip('bash unavailable')
    source = (ROOT / 'deploy/docker/calb-maintenance.sh').read_text(encoding='utf-8')
    function = source[source.index('cleanup_old_calb_images()'):source.index('maybe_vacuum_global_journal()')]
    script = '''set -eu
DEFAULT_PROJECT_NAME=calb-sizingtool
DEFAULT_IMAGE_NAME=calb-sizingtool
docker() {
 case "$1" in
 ps) echo current-container ;;
 inspect) echo sha256:running ;;
 images)
   case "$*" in
   *Tag*) printf 'sha256:running ubuntu\\nsha256:previous rollback-previous\\nsha256:previous old-tag\\nsha256:old old\\n' ;;
   *) printf 'sha256:running\\nsha256:previous\\nsha256:old\\n' ;;
   esac ;;
 image) echo "$3" >> "$DELETE_LOG" ;;
 esac
}
'''
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        log = Path(scratch) / 'deleted'
        env = dict(os.environ, DELETE_LOG=log.as_posix())
        subprocess.run([bash], input=script + function + '\ncleanup_old_calb_images\n', text=True, check=True, env=env, capture_output=True)
        assert log.read_text().splitlines() == ['sha256:old']


def test_report_figure_logs_distinguish_svg_and_failure(caplog, monkeypatch):
    import logging
    from calb_sizing_tool.ui.report_export_view import _log_figure_resolution
    from calb_sizing_tool.ui.report_export_view import _log
    # Alembic fileConfig in the app tests disables pre-existing loggers.
    monkeypatch.setattr(_log, 'disabled', False)
    monkeypatch.setattr(_log, 'propagate', True)
    with caplog.at_level(logging.INFO, logger=_log.name):
        _log_figure_resolution('SLD', None, b'<svg/>', [], dc_run_id='dc-1', artifact_run_id='ac-2')
        _log_figure_resolution('Layout', None, None, ['registry unreadable'], dc_run_id='dc-1', artifact_run_id='ac-2')
    assert 'status=available dc_run=dc-1 artifact_run=ac-2' in caplog.text
    assert 'status=read_failed' in caplog.text
    assert caplog.records[0].levelno == logging.INFO
    assert caplog.records[1].levelno == logging.WARNING

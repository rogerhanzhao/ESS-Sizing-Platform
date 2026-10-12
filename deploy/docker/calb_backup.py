"""CALB-local recovery archive: consistent SQLite, outputs, preferences, config.

Runs on the host before cleanup/deployment. Archives contain private data and
must stay outside Git. A published archive has passed a restore/read-back check.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from uuid import uuid4


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _hash_stream(stream)


def _hash_stream(stream) -> str:
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(chunk)
    return h.hexdigest()


def verify_archive(archive: Path) -> dict:
    """Read every archived file and restore the DB into a disposable directory."""
    with tarfile.open(archive, 'r:gz') as tar, tempfile.TemporaryDirectory() as scratch:
        manifest = json.load(tar.extractfile('manifest.json'))
        files = manifest['files']
        members = tar.getmembers()
        if len(members) != len(files) + 1 or {m.name for m in members} != set(files) | {'manifest.json'}:
            raise ValueError('Archive member list does not match its manifest')
        for member in members:
            if not member.isfile():
                raise ValueError('Archive contains a non-file member')
            if member.name == 'manifest.json':
                continue
            with tar.extractfile(member) as stream:
                if _hash_stream(stream) != files[member.name]:
                    raise ValueError('Archive checksum mismatch: ' + member.name)
        db_name = manifest['database']
        restored_db = Path(scratch) / 'restored.sqlite'
        with tar.extractfile(db_name) as source, restored_db.open('wb') as target:
            shutil.copyfileobj(source, target)
        with closing(sqlite3.connect(restored_db.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('pragma integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Restored database integrity check failed')
    return {'files': len(files), 'database_integrity': 'ok', 'sha256': digest(archive)}


def create_backup(runtime: Path, env_file: Path, *, label='manual', keep=8) -> Path:
    if label not in {'manual', 'scheduled', 'predeploy'} or keep < 1:
        raise ValueError('Invalid backup label or retention count')
    runtime = runtime.resolve(strict=True)
    source_db = runtime / 'state' / 'calb_sizing.sqlite'
    if not source_db.is_file() or not env_file.is_file():
        raise FileNotFoundError('Database or deployment configuration is missing')
    # Do not silently back up a different DB if a deployment overrides the URL.
    db_url = os.environ.get('CALB_DATABASE_URL', 'sqlite:////app/runtime/state/calb_sizing.sqlite')
    if db_url != 'sqlite:////app/runtime/state/calb_sizing.sqlite':
        raise ValueError('Non-default database URL requires an explicit backup procedure')
    backup_dir = runtime / 'backups'
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive = backup_dir / f'{label}-{stamp}-{uuid4().hex[:8]}.tar.gz'
    partial = archive.with_suffix('.partial')
    try:
        with tempfile.TemporaryDirectory(prefix='.calb-backup-', dir=backup_dir) as scratch:
            stage = Path(scratch)
            (stage / 'state').mkdir()
            snapshot_path = stage / 'state/calb_sizing.sqlite'
            with closing(sqlite3.connect(source_db.as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(snapshot_path)) as target:
                    source.backup(target)
            outputs = runtime / 'outputs'
            if outputs.exists():
                for path in outputs.rglob('*'):
                    if path.is_symlink():
                        raise ValueError('Output symlinks require review before backup')
                    if path.is_file():
                        destination = stage / 'outputs' / path.relative_to(outputs)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, destination)
            # Validate that the DB snapshot's registered files survived the copy.
            # A concurrent regeneration/cleanup can otherwise create a false backup.
            with closing(sqlite3.connect(snapshot_path)) as db:
                for path, expected in db.execute('select file_path,content_hash from artifact_registry'):
                    relative = Path(path)
                    if relative.is_absolute():
                        relative = relative.relative_to('/app/runtime/outputs')
                    candidate = (stage / 'outputs' / relative).resolve()
                    if not candidate.is_relative_to(stage / 'outputs') or not candidate.is_file():
                        raise ValueError('Registered output missing from backup: ' + str(path))
                    if expected and digest(candidate) != expected:
                        raise ValueError('Registered output changed during backup: ' + str(path))
            preferences = runtime / 'state/user_preferences.json'
            if preferences.exists():
                shutil.copy2(preferences, stage / 'state/user_preferences.json')
            (stage / 'config').mkdir()
            shutil.copy2(env_file, stage / 'config/deploy.env')
            files = {p.relative_to(stage).as_posix(): digest(p) for p in stage.rglob('*') if p.is_file()}
            manifest = {'created_at': stamp, 'database': 'state/calb_sizing.sqlite', 'files': files}
            (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            # Set permissions before opening the archive, not after secrets are written.
            fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as raw, tarfile.open(fileobj=raw, mode='w:gz') as tar:
                for path in sorted(stage.rglob('*')):
                    if path.is_file():
                        tar.add(path, arcname=path.relative_to(stage).as_posix(), recursive=False)
            verify_archive(partial)
            partial.replace(archive)
        # Bound automated growth; deliberately created manual copies stay.
        if label in {'scheduled', 'predeploy'}:
            for old in sorted(backup_dir.glob(f'{label}-*.tar.gz'), key=lambda p: p.stat().st_mtime_ns, reverse=True)[keep:]:
                old.unlink()
        return archive
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--runtime', type=Path, default=Path(os.environ.get('CALB_RUNTIME_ROOT', '/opt/calb-sizingtool/runtime')))
    parser.add_argument('--env-file', type=Path, default=Path(__file__).with_name('.env'))
    parser.add_argument('--label', choices=['manual', 'scheduled', 'predeploy'], default='manual')
    parser.add_argument('--keep', type=int, default=int(os.environ.get('CALB_BACKUP_KEEP', '8')))
    args = parser.parse_args()
    archive = args.verify or create_backup(args.runtime, args.env_file, label=args.label, keep=args.keep)
    print(json.dumps({'archive': str(archive), **verify_archive(archive)}))


if __name__ == '__main__':
    main()

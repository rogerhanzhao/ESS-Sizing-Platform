# CALB recovery points

`calb-serverctl.sh start/restart/update` backs up an existing running deployment
before rebuilding it and tags its image as `calb-sizingtool:rollback-previous`
(or the configured `CALB_IMAGE_NAME`). Scoped maintenance preserves every image
with a `rollback-*` tag and uses full image IDs for comparisons.

The existing weekly maintenance service now runs `calb_backup.py --label scheduled`
before cleanup. Backup failure stops cleanup. The host needs Python 3.10+.

The archive contains a consistent SQLite backup, runtime outputs, user preferences
when present, deployment `.env`, and a SHA-256 manifest. Every registered output
must exist and match its stored content hash; a racing regeneration or pre-existing
missing file fails the backup rather than publishing an incomplete recovery point.
The archive is reread and its database restored into a temporary directory for an
integrity check before publication. This is a data restore check, not a complete
application disaster-recovery drill.

Archives are private, mode 0600, in `CALB_RUNTIME_ROOT/backups`. Never commit or
publish them: they contain customer data and deployment credentials. Scheduled and
predeploy archives each retain the latest `CALB_BACKUP_KEEP` copies (default 8).
Manually labelled archives and older backup formats are not automatically deleted.
This local backup does not protect against loss of the host; use an independently
managed off-host copy for that requirement.

Verify an archive without changing the running application:

```sh
python3 deploy/docker/calb_backup.py --verify /path/to/archive.tar.gz
```

For recovery, first verify the chosen archive, stop only the CALB application and
save the current runtime as a separate recovery point. Restore the archive's
`state/calb_sizing.sqlite`, `outputs/`, optional preferences, and reviewed deployment
configuration to the corresponding runtime/configuration locations. Do not reuse
WAL/SHM files belonging to the replaced database. Start the matching preserved
image without rebuilding it and check application version, health and a restored
run before making the service available. Keep the original archive intact.

The backup helper intentionally supports the current default SQLite location only.
A custom `CALB_DATABASE_URL` fails explicitly and requires its own verified backup
procedure; it never silently backs up the default file instead.

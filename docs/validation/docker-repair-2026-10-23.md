# Docker runtime recovery — Sprint 18

Desktop startup failed on a stale `Docker/run/dockerInference` runtime socket.
The engine pipe was absent; logs identified the same socket-removal failure as
the earlier October repair records. No application database issue was inferred.

After confirming Desktop/backend processes were stopped, a bounded helper checked
the two exact runtime folders for zero-byte reparse socket entries only, with no
subdirectories or other data. It preserved the folders as:

- `C:/Users/mikae/AppData/Local/Docker/run.sprint18-backup-20261023`
- `C:/Users/mikae/AppData/Local/docker-secrets-engine.sprint18-backup-20261023`

The second folder was recreated during recovery before the helper's New-Item
step, which reported an already-existing directory. Read-only inspection verified
the new directory was empty and both backups existed; Desktop was then started.
The Docker API answered, and only the existing `intraspot-mvp-postgres-1` container
was explicitly started. Its health check passed and PostgreSQL remained bound to
`127.0.0.1:5433` with its existing volume.

No recursive deletion, factory reset, image/container removal, credential edits,
database reset or Penpot database access. The socket backups remain recoverable.

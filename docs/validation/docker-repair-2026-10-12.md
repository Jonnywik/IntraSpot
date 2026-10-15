# Docker recovery — 2026-10-12

The user explicitly authorized Docker repair after choosing initially to restart it themselves. The investigation-first workflow isolated startup failures before changing runtime state.

## Observed cause

Docker Desktop 4.85.0 stopped during startup with Windows error 1920 while opening/removing its Unix runtime sockets. The Windows `afunix` driver was already running, so no driver/service configuration was changed. Individual socket rename and reparse-metadata clearing both failed without changing the files. Clearing the first runtime location exposed another stale socket; a failed intermediate startup also left a newly created runtime socket behind.

## Recoverable repair

Stopped the crashed Desktop through its supported `docker desktop stop --force --timeout 15` command. Verified exact absolute paths, stopped backend processes, and enumerated contents before each directory rename. Only zero-byte socket files were present at the selected locations. Renamed the containing runtime folders to backups, created fresh runtime folders, and restarted through `docker desktop start --timeout 30`.

Backups retained outside the project:

- `C:/Users/mikae/AppData/Local/Docker/run.phase2-backup-20261012`
- `C:/Users/mikae/AppData/Local/Docker/run.phase2-backup-20261012-02`
- `C:/Users/mikae/AppData/Local/docker-secrets-engine.phase2-backup-20261012`

No recursive deletion, factory reset, reinstall, credential-file change, database reset, or volume deletion occurred. The original sockets remain in those backups. These are runtime endpoints, not database files.

## Verified recovery

- Docker's engine answered `docker ps` successfully.
- Existing Penpot containers restarted through their existing policies. Penpot PostgreSQL 15 and Valkey reported healthy; no Penpot configuration or database operation was performed.
- Started only the separate `intraspot-mvp` PostgreSQL service using its existing Compose configuration.
- Inspected MVP container: image `postgres:17`, healthy, bound only to `127.0.0.1:5433`, existing volume `intraspot-mvp_mvp-data`.
- Alembic drift check against the local MVP database returned `No new upgrade operations detected.`

The repair restored the local test dependency; it does not grant deployment or real-user approval. Official references: [Docker Desktop stop](https://docs.docker.com/reference/cli/docker/desktop/stop/), [Windows Unix sockets and reparse points](https://devblogs.microsoft.com/commandline/af_unix-comes-to-windows/).

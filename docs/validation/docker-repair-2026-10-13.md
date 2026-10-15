# Docker runtime recovery — 2026-10-13

Normal Docker Desktop startup failed on `Docker/run/dockerInference`: a stale zero-byte AF_UNIX reparse socket could not be removed. The Docker API was initially absent. No application source or database volume explained this startup failure.

After confirming Docker was stopped, the coordinator validated the two exact runtime directories: all entries were zero-byte reparse points, with no subdirectories or other data. The directories were recoverably moved, not deleted:

- `C:/Users/mikae/AppData/Local/Docker/run.sprint3-backup-20261013`
- `C:/Users/mikae/AppData/Local/docker-secrets-engine.sprint3-backup-20261013`

Fresh runtime directories were created and Docker Desktop restarted. Its command timed out while initialization continued, but the subsequent Docker API check succeeded and existing Penpot containers reappeared. The coordinator started only `intraspot-mvp`'s dedicated PostgreSQL 17 service on loopback port 5433, using its preserved volume. Compose reported that container healthy.

No container removal, factory reset, image deletion, database reset or Penpot database change was performed. Socket backups remain recoverable. This restores the test prerequisite, not proof that the underlying Windows socket issue cannot recur.

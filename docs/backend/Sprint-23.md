# Sprint 23 — integrated developer verification and handoff

Scope frozen 2026-10-24. Verify the implemented Sprint 1–22 system as a local
development checkpoint, repair demonstrated integration defects, and publish the
checkpoint to GitHub. No new product behavior, redesign, deployment, cloud app
database/media migration, live credential entry or participant study.

## Work and proof

- Run the whole default PostgreSQL suite serially against its named scratch DB;
  run the separate synthetic-auth suite afterward. Reuse unchanged results only
  with matching source; rerun affected tests after demonstrated fixes.
- Review current identity/privacy, authority, registration capacity/FIFO,
  idempotency, deadlines, ownership, attendance and safety boundaries together.
  Luna/max workers have disjoint review/fix scopes; the coordinator owns shared
  integration, dependency locks, serial execution and delivery.
- Resolve verified frontend security advisories with compatible targeted updates,
  never suppress the advisory or run an unreviewed automatic upgrade directive.
  Preserve the local fictional and real-auth build separation. Run audit, Node
  checks, lint/types, public-asset guard and both exports.
- Verify live API readiness, exported static routes and browser-origin preflight
  behavior. HTTP/export checks do not establish live DOM, focus or visual behavior.
  Use only an available permitted browser; never bypass a browser-policy denial.
- Verify both existing development datasets are unchanged, Alembic metadata has no
  drift, no startup migration occurs, and local operation instructions are current.
  Do not reset databases/volumes or touch Penpot.
- Write an integrated handoff, verification matrix, reproducible local commands
  and explicit open gates. Bring the canonical Obsidian checkpoint and repository
  entrypoint up to date. Commit/push after verification; no force push.

## Stop condition

Complete this developer checkpoint once supported checks pass and every failed,
blocked or unavailable gate is recorded honestly. Participant testing and real-user
release require separate authorization. Live PLM sign-in, native-device/full
accessibility matrix, unresolved retention/hosting operations and deployment are
not inferred from automated checks. Do not start an invented Sprint 24.

# Deployment preparation: Sprints 25–30

Authorized by the user on 2026-10-26. This is an implementation sequence,
not permission for public exposure or paid infrastructure. Each verified sprint
is committed and pushed separately. Canonical decisions remain in Obsidian.

| Sprint | Deliverable | Required proof |
| --- | --- | --- |
| 25 | Hosted configuration, isolated DB roles, container and CI | Unsafe settings denied; local profiles intact; disposable PostgreSQL permission checks |
| 26 | Private durable media, reservations/quotas and reconciliation | Restart/two-instance reads; immediate access revocation; concurrent quota safety |
| 27 | Bounded maintenance, shared limits and sanitized operations | Outage recovery; contention/restart; no duplicate effects or leaked data |
| 28 | Paired recovery, retention and operator-mediated erasure | Isolated restore; hash equality; holds/ownership and repeat-safe cleanup |
| 29 | Critical-flow accessibility and recovery feedback | Six-view matrix including details/registration/results; human checks separate |
| 30 | Integrated candidate and deployment rehearsal | Fresh regression, 25 sessions, rollback and honest release ledger |

## Frozen contracts

- `INTRASPOT_CONFIG=hosted` reads process environment only. Hosted auth is
  Supabase, fixture auth is false, and frontend/API origins are exact HTTPS roots.
- Frontend `NEXT_PUBLIC_DEPLOYMENT=hosted`, `NEXT_PUBLIC_FRONTEND_ORIGIN`,
  `NEXT_PUBLIC_API_URL`, Supabase public configuration; no local environment-file
  inheritance. Existing local profiles stay unchanged.
- Hosted runtime uses session pooling, verified TLS, one API process and a 3+2
  connection ceiling. Migration credentials are separate and never served.
- Hosted media remains behind `/api/v1/media/{id}`, with a private remote bucket;
  metadata contains stable IDs and server-only keys. No direct bucket grants.
- Orchestrator owns shared migrations, locks, router/OpenAPI, CI, canonical notes
  and Git. Builders have disjoint file ownership; Luna/max QA reviews independently.

## Release boundaries

No local personal/fictional data import into a real-user environment. Existing
datasets and historical generated evidence are preserved. Recurring budget is
$0. Koyeb Free is an evaluation host, not a production availability promise.
Participant/device/screen-reader and positive PLM checks are not satisfied by
synthetic tests. The user deferred PLM verification; do not resume it implicitly.
Provider credentials, actual cloud configuration and public release require
their own available access and explicit release action.

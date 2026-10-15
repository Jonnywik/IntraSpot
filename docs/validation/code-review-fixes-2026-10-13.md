# Code-review repair validation — 2026-10-13

Scope: repair the findings from the code pass, keeping approximately 5% of the current usage allowance in reserve. Local fictional MVP only. This does not accept the full Sprint 4 or Sprint 5 or authorize release.

## Fixed

- Withdrawal saves cancellation, earliest-waiter promotion and notification in the same locked transaction. Both confirmed and waitlisted active registrations reject withdrawal after start; cancelled retries remain idempotent.
- Summary length is capped consistently at 200 characters in draft input and publication validation, including pre-existing drafts.
- Additive migration `mvp_0002` rejects incomplete published events and invalid start/end ordering. Incomplete drafts remain supported. Downgrade drops only the added constraint. Existing invalid rows cause upgrade to roll back, with no silent data repairs.
- Public discovery fetches committed confirmed counts using one grouped query for the page, preserving search, My Clubs, ordering and pagination.
- The quality test receives its missing fixture; approved public organization and read-only discovery expectations match the contract. The query-count test now measures each request independently and tests ten events. The withdrawal route test also checks persisted My Events state.
- OpenAPI regenerated with pagination and the summary bound.
- Frontend event details label confirmed attendance correctly instead of calling it interest.

## Evidence

- Initial review: **143 passed, 13 failed** against the dedicated PostgreSQL test database.
- Repaired combined suite: **158 passed**, with the two existing dependency/metadata warnings, in 121.73 seconds.
- Two additional focused regressions: **2 passed** in 5.29 seconds. They prove notification failure rolls back cancellation/promotion, and bounded backlog passes commit before promotion. These were added after the combined run collected its tests.
- Migration tests verify downgrade/upgrade preserves existing events and that invalid existing rows fail upgrade without rewriting data or advancing the revision.
- Development migration upgraded explicitly to `mvp_0002`; `alembic check` reports no new upgrade operations.
- Development data was preserved across migration: all eight application tables have the same complete-row digest before/after (`48cef20f78c123cdee617b87e5cae23cc756e179b063eee4012536a1d3e4a248`), including all 13 event rows. No Penpot database was accessed.
- Existing local API launcher/child were verified by command line and restarted on port 8001. Live HTTP checks return health/ready 200, revision `mvp_0002`, a two-event page and the pagination parameters in served OpenAPI.

## Frontend checks

The initial lint check failed because the installed `is-extglob` entry file was missing. A sandboxed lockfile reinstall was blocked at `node_modules/.bin`; the exact lockfile reinstall completed outside the sandbox. No dependency upgrade was requested.

- `npm run lint`: passed.
- TypeScript `--noEmit --incremental false`: passed.
- `npm run build`: passed, including compilation, TypeScript and page generation. The first sandboxed build could not canonicalize the OneDrive path; the same build succeeded outside the sandbox without a source workaround.
- Local credentials, signing keys, account tokens and installed dependencies remain ignored by Git.

## Completion and usage reserve

All reported repair targets are verified. The usage window refreshed during the dependency reinstall; no reset credit was redeemed by this agent. Stop after the completed repairs rather than spending the refreshed allowance on unrelated work. Two pre-existing backend dependency/field-metadata warnings remain. Browser presentation and participant testing were not part of this repair pass.

# Sprint 4 acceptance — 2026-10-13

## Scope

Local backend registration/waitlist milestone only, using fictional identities
and PostgreSQL 17. Sprint 5 frontend integration, Penpot, real authentication,
cloud services and deployment were not changed. The main chat coordinated four
GPT-6 Luna/max workers with disjoint acceptance files, then reviewed their work,
fixed production code and ran all database tests serially.

## Completed behavior

- Eligible, profile-complete accounts register for future published events.
- Three seats remain three seats under ten competing attempts; overflow joins
  the waitlist with an immediate position and no estimated wait time.
- Receipt admission order is durably assigned by the server. A stored retry
  returns its original outcome even after promotion or withdrawal.
- Incompatible key reuse conflicts; another key cannot create a second active
  registration or consume an extra seat.
- Pre-start withdrawals atomically promote the earliest waiter and persist one
  in-app notification. Concurrent/repeated withdrawals do not duplicate it.
- My Events returns only the caller's current/latest registration per event,
  including historical Past events. Notification reads are caller-only.
- A committed intake survives one process exiting before drain. A separate
  process recovers it, preserving the immutable retry result.
- A real loopback HTTP API demonstrates capacity, promotion and privacy, then
  restarts as a different instance and retains outcomes and notifications.

## Additional defect fixed

Separate event batches can contain shared users in opposite receipt orders.
Locking each user's row while processing that order permits a cross-event lock
inversion. Batches now prelock their distinct users in ascending user-ID order
before processing receipts in unchanged event order. The independent regression
captures the actual PostgreSQL locking queries for opposite-order batches and
also verifies that lock order does not change which attendee receives the seat.
This is a lock-order regression proof, not a claim that a production deadlock
was observed with real users.

No migration or dependency change was needed. Public discovery/detail reads
remain read-only; recovery runs on submission, withdrawal or personal listing.

## Verification checkpoint

- Pre-fix combined suite: **172 passed**, one dependency deprecation warning,
  93.34 seconds.
- Post-fix focused registration, race, API, recovery, locking and HTTP checks:
  **28 passed**, one dependency deprecation warning, 31.90 seconds.
- Final combined gate after strengthening receipt-order proof: **173 passed**,
  one dependency deprecation warning, 103.22 seconds.
- Alembic schema drift check: **no new upgrade operations detected**.
- Refreshed local API on `127.0.0.1:8001`: health **ok**, readiness **ready**
  at migration `mvp_0002`, public discovery responds successfully.
- Full-suite OpenAPI freshness regression checks served contracts against the
  saved `docs/backend/openapi.json`; endpoints and schemas are unchanged.

The test fixtures guard and reset only `intraspot_mvp_test` on loopback 5433.
Development records and the separate Penpot database were not reset or migrated.
The isolated HTTP test stops its own spawned API processes in cleanup. No
tokens, emails, profiles or full request bodies were printed in this report.

## Limitations and next gate

One upstream Starlette/httpx TestClient deprecation warning remains. Recovery
is request-driven rather than an unattended worker. Approval registrations,
chat, attendee UI integration and real-user release remain outside this sprint.
Sprint 5 is next: integrate the approved frontend with these persisted APIs.
Participant validation and security/release checks remain mandatory before a
real-user pilot.

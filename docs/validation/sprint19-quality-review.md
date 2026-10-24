# Sprint 19 backend quality review

Date: 2026-10-22

## Scope

Added independent PostgreSQL API, lifecycle, scheduling, concurrency, and public
projection tests under `Code/Backend/tests/featured/`. The coordinator owns the
shared implementation and serial database slot. The coordinator's migration
roundtrip, populated downgrade refusal, and direct exclusion/adjacency checks are
covered in `Code/Backend/tests/shared/test_sprint19_infrastructure.py` and are
not duplicated here.

## Coverage added

- Manager eligibility, moderator/member/inactive-role denial, cross-organization
  isolation, platform-admin authorization from database state, and server-derived
  audit actors.
- Published/approved/future-event eligibility, idempotent pending retries,
  historical rejected/revoked requests, stale versions, and strict decision input.
- Timezone-aware approval windows, validation boundaries, omitted/null start
  defaults, overlap conflicts, adjacent API schedules, and concurrent approvals
  across different events.
- Concurrent same-event requests returning one pending request; approve, material
  event-change pause, fresh review, and revoke behavior.
- Lazy effective expiry without read-time writes, material fingerprint fail-closed
  behavior, persistence after application recreation, and half-open active-time
  boundaries.
- Batched Featured lookups on public feed, search, My Clubs, Saved Events, and My
  Events; existing sort order and public audit privacy.
- Platform history bounded to 100 rows.

## Pre-integration findings and coordinator resolution

- Stored `expired` is intentional only on the new-request write path, to seal an
  expired open row before re-requesting. GETs remain read-only, verified by tests.
- Canonical notes are reconciled with the newer accepted badge-only roadmap and
  the user's explicit material-change pause/fresh-review choice.

## Verification status

The independent worker compiled tests without running the shared database. The
coordinator subsequently ran the serial suites: corrected feature/migration gate
27 passed; broader regression 546 passed with two expectation updates subsequently
passing, plus two new regression checks. This gives 550 unique passing default
cases across runs; 50 synthetic-auth checks also passed. See the acceptance record
for the exact evidence, browser checks and unclosed release gates.

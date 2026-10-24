# Sprint 22 quality review

Coordinator addendum, 2026-10-24: the retained-terminal-banner finding below is
fixed through the existing private manager path. All seven final HTTP cases pass
after correcting the approval fixture's required review window and the nested
registration-review assertion. The domain/visibility/migration run passed 37;
see [integrated evidence](sprint-22-acceptance-2026-10-24.md) for checks and open
browser/security gates. These are coordinator executions, not independent
participant or live-browser results. Initial source observations below are kept
as the assessor's review record.

**Status:** Static interface review complete. Six test functions cover eight
HTTP journey paths in `Code/Backend/tests/quality/test_sprint22_quality.py`;
the coordinator owns the serial PostgreSQL run. The frozen contract in
`docs/backend/Sprint-22.md` is the test oracle.

## Coverage

1. Report receipt retries, evidence privacy, and escalation on the third
   distinct post-review reporter; a report alone does not hide an event.
2. Organization/platform action authority, independent hide/restore channels,
   terminal non-resurrection, and platform removal of a draft followed by
   denied PATCH, banner upload, and publish using the current GET-draft
   `draft_version` as `If-Match`.
3. Exact suspension expiry at `suspended_until`, followed by repeated reads
   from a fresh app instance; one system audit and one expiry notice.
4. Direct registration bypass attempts during hide/suspension, while existing
   FIFO promotion, approval review, participant detail, and chat continue.
5. Both removal and cancellation (parameterized): registration cancellation,
   durable 409 sealing plus HTTP retry of a preexisting unprocessed receipt,
   exact retry of an original completed receipt, deduplicated notices, no
   attendance writes, and terminal banner visibility rules.
6. Stale safety versions, incompatible key reuse, exact retry, and authority
   rechecks after organization-role/platform-admin revocation.

## Confirmed contract comparisons

The four event-safety models and their migration fields, foreign keys, enum and
version checks, indexes, and audit uniqueness match the frozen definitions.
Request schemas use the specified action/reason enums and version bounds;
receipt/review/projection names match. `SafetyAuditOut` excludes payload hashes,
client keys, and previous/result snapshots. The service applies the seven-day
suspension default and rejects duration on resume.

`app/core/event_safety.py` exposes the eight specified read-only helpers. The
shared predicate excludes either hide, terminal events, and suspensions while
`suspended_until > at`. Restricted new registration returns the implemented
409 `event_registration_unavailable`; unreadable public detail returns 404
`event_not_found`. Authorized staff and active registration states can read
restricted nonterminal events.

Migration `mvp_0017` follows `mvp_0016` and adds the four safety tables. Its
downgrade refuses to drop them when safety data exists. The service uses the
inclusive expiry boundary (`suspended_until <= at`), clears the expiry, increments
version, and writes one actorless audit plus one in-app notice under the org
lock. Current authority checks precede privileged idempotent replay.

The saved integration call sites check new registration after taking the event
write lock and before creating an outcome; existing receipt retries are checked
first. FIFO promotion is blocked only for terminal events. Removal/cancellation
uses the shared registration hook, which cancels active participation, clears
review/reconfirmation fields, seals unprocessed receipts, and sends deduplicated
in-app notices. The attendance service rejects terminal writes and the terminal
hook does not edit attendance rows.

## Confirmed finding; coordinator patch pending

**Terminal banner access skipped the existing private staff path at review.**
The media reader used `_private_access` only when the event was unpublished or
its organization was not approved. A removed/cancelled event remains published
and approved, so the reader fell through to `can_read_event`; that policy
returns false for terminal events and the owner/admin receives 404. The frozen
contract requires terminal banner access to use the existing private staff
path. The terminal HTTP journey asserts anonymous 404 and owner access. The
coordinator acknowledged the finding and plans to route terminal reads through
the existing private path; close it after the serial HTTP case passes.

References: [media service](/C:/Users/mikae/OneDrive/Desktop/Codes/Projects/IntraSpot/Code/Backend/app/domains/media/service.py:211), [terminal read policy](/C:/Users/mikae/OneDrive/Desktop/Codes/Projects/IntraSpot/Code/Backend/app/core/event_safety.py:78).

## Verification boundary

No DB suite, build, migration, or Git command was run by this QA worker. The
banner finding was confirmed from source before the coordinator's planned fix;
the serial HTTP run remains the completion check for all six tests.

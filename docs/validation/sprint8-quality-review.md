# Sprint 8 quality review

Date: 2026-10-15

This is a quality-assessor review, not evidence that Sprint 8 is complete. The
frozen contract is `docs/backend/Sprint-8.md`; this review and the independent
API regressions are the only files changed for this task.

## Source review findings

1. **The chat access gate now checks trusted eligibility, but notification
   delivery does not.** `Code/Backend/app/domains/chat/service.py:53-68`
   checks the current stored user's active and PLM-eligibility state in the
   shared confirmed-access path; `service.py:104-105` applies it to the inbox,
   and `service.py:281-282` rechecks it after the send user-row lock. However,
   the recipient fan-out at `service.py:305-319` selects confirmed, unrevoked
   registrations without checking current recipient eligibility. The
   `/me/notifications` route returns those rows by user ID alone, including
   `event_id`, `kind`, and `message` (`Code/Backend/app/notifications.py:68-86`).
   If an attendee becomes unverified after confirmation, another attendee's
   message still creates a visible "New message in an event chat" notice for
   them, even though the chat inbox and thread are denied. Filter new fan-out
   recipients by trusted eligibility and suppress existing `chat_message`
   notices while the recipient is ineligible; otherwise an ineligible attendee
   still learns chat activity and its event ID.

2. **At the earlier integration checkpoint, membership API integration was
   still in progress.**
   `Code/Backend/app/api/router.py:13-14` imports both membership route modules,
   but that checkpoint's observed file inventory contained `models.py`,
   `schemas.py`, `policy.py`, `access.py`, `routes_access.py`, and
   `tests/memberships/test_access.py` only. `routes_applications.py` was absent
   then, so app creation could not yet import the full Sprint 8 API. Main should
   re-check this integration as the application worker finishes; this historical
   checkpoint is not a claim about the current file inventory.

3. The coordinator's registration seam currently locks published organization
   events in ID order, stores an admission cutoff, cancels current participation,
   and promotes waiters in `Code/Backend/app/domains/registrations/service.py:1017-1061`.
   Pending receipts are drained later by `catch_up_event` and rejected when their
   order is at or below that stored cutoff (`service.py:404-425, 673-690`). This
   is source review only; the fresh-process receipt regression has not run.

## Independent regressions added

`Code/Backend/tests/shared/test_sprint8_quality.py` adds seven API-level cases:

- An approved, unverified account remains locked from both the chat inbox and
  event thread; trusted stored eligibility becoming true updates `access_ready`,
  restores both chat views, and leaves the approved role as `member`.
- Membership persona visibility requires its own application consent, ignores
  global persona visibility, and disappears from closed reviews.
- Rejection permits a new application immediately; withdrawal exposes the exact
  24-hour reapplication time and blocks a new-key retry during the cooldown.
- Invitations are recipient-bound, cannot restore a departed grant on replay,
  expire at the boundary, and cannot be accepted after revocation.
- Ordinary members and moderators cannot use staff-only roster, audit, invitation,
  or role-management actions; owner role change, removal, and leave are rejected.
- Leaving cancels active registrations, promotes a waiter, preserves ended
  attendance, revokes active and archived chat, and keeps an old pending receipt
  denied when a separate process drains it after departure. A later registration
  with a new order remains possible.
- Removal retries return the stored result, incompatible reuse of the same key
  returns 409, and concurrent removals promote waiters without exceeding event
  capacity or restoring chat for departed members.

These checks exercise HTTP routes and persisted outcomes across the shared
domains. They do not repeat every service-level assertion in
`tests/memberships/test_access.py` or the existing registration suite.

## Test proof and remaining limits

- The new Python file passed an in-memory AST syntax parse using
  `Code/Backend/.mvp-venv/Scripts/python.exe`.
- Ruff was unavailable in the current `.mvp-venv` (`ruff.exe` was not present),
  so no lint result is claimed.
- No pytest command, database reset, migration, or test subprocess was run. The
  serial PostgreSQL slot has not been assigned. All seven database-backed tests
  remain unexecuted and need that slot after application routes, policy, and
  shared integration are present.
- No production implementation, migration, generated type, canonical note, or
  other worker-owned file was edited.

## Coordinator resolution and executed proof

The sections above preserve the independent worker's earlier checkpoint, not the
final integration status. The coordinator subsequently integrated both route
modules, the frontend entry points, shared registration/chat access seams,
organization notifications and explicit `mvp_0006` migration.

- Finding 1 is fixed: chat fan-out requires current active trusted eligibility;
  existing chat-activity notices are hidden and cannot be marked read while the
  caller is ineligible. A dedicated HTTP regression proves loss/restoration.
- Finding 2 is resolved: the final application creates successfully with both
  membership routers, and the generated OpenAPI/types include the reviewed APIs.
- Finding 3 is verified by the independent-process pending-receipt test, concurrent
  departure checks and a separate legacy registration-without-receipt regression.
- Expired invitation actions, unavailable recipients, operation notices, My Clubs
  actor refresh and ambiguous chat joins were also corrected during integration.

The coordinator ran the entire serial PostgreSQL suite on 2026-10-15:
**294 passed, 4 opt-in browser tests skipped, 1 upstream warning, 299.09 seconds.**
This includes all seven independent quality regressions and both membership
domain suites. The skips are separate rendered-browser gates, not untested
membership API cases. The Sprint 8 rendered browser gate independently passed
nine journey groups; the final combined browser rerun is recorded in the
[acceptance report](sprint-8-acceptance-2026-10-15.md).

Frontend contract tests passed all nine checks; lint, the isolated static build,
TypeScript and credential scans passed. Development schema drift checking found
no new upgrade operations. No participant or real-user deployment approval is
claimed.

Final follow-up: all four rendered browser suites passed serially, **4 passed in
102.31 seconds**, covering 36 journey groups. The normal API 8001 frontend rebuild
also passed after a Windows generated-folder permission retry, with no source or
cache deletion. Live normal frontend/API probes succeeded and the deadline worker
was restored. Complete evidence and remaining limits are in the acceptance report.

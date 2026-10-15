# Sprint 7 quality review

Date: 2026-10-14  
Contract reviewed: `docs/backend/Sprint-7.md`  
Scope: `Code/Backend/tests/shared/test_sprint7_quality.py` and read-only review of Sprint 7 workers.

## Regression coverage added

The serial PostgreSQL integration module adds eight bounded cases covering guest comment privacy and all six reaction states; capacity and seat invariants; comment/reaction start boundaries; concurrent idempotency and report deduplication; confirmed-chat authorization, withdrawal, reconfirmation and retention; report-role isolation, reporter-only hides, resolution and evidence retention; pending personal restrictions with read/reaction access and existing-seat preservation; and restart-safe report escalation/expiry, notice deduplication and chat cleanup.

The pending-person case now models one confirmed attendee in a capacity-one event and asserts `confirmed_count == 1`, `reserved_count == 0`, and `remaining_spots == 0`. It also checks that an existing comment and chat message replay with the same client key return their original IDs and HTTP 200, while genuinely new comment/chat writes are denied. It verifies that event-draft creation and publication are denied without cancelling the attendee's confirmed seat. The chat authorization case separately asserts that a same-key replay is denied after withdrawal.

Main reported a serial QA run with five tests passing before the role-isolation case failed: its foreign-organization query used `other_org`, which is owned by `other_owner`, so an empty 200 response was legitimate. The test now denies `other_owner` access to the report's original `organization` and separately asserts that their own organization returns 200 with an empty list. This correction has not been rerun. I did not run PostgreSQL tests; the shared fixture truncates `intraspot_mvp_test`, and the serial slot remains with Chat.

## Previously reported source findings — rechecked after main's fixes

The four findings below are addressed in the current source snapshot, consistent with Main's report. This is source inspection, not independent database-backed verification.

1. **Comment retries preserve the original outcome under a partial personal restriction.** `Code/Backend/app/domains/social/service.py:195-225` resolves the existing author/event/client-key comment before applying the communication restriction to a new comment; new writes still get the pre-start and restriction checks.

2. **Reaction/comment write time is sampled after event locking.** `Code/Backend/app/domains/social/service.py:92-94,195-225` locks the published event before obtaining the write timestamp; the write routes no longer supply a pre-lock timestamp. Comment creation also rechecks after acquiring the communication lock.

3. **Active-report retries return the reporter's receipt before rechecking target visibility.** `Code/Backend/app/domains/moderation/service.py:279-284` checks confirmed-chat access first for message reports, then returns that reporter's active report before target-visibility checks. The access guard remains in force.

4. **Chat event IDs receive UUID request validation.** Both event-chat routes use `id: UUID` in `Code/Backend/app/domains/chat/routes.py:25,45` and pass the validated value to the service as a string.

## Unresolved frozen-contract risk

**Coordinator resolution, 2026-10-15:** the note below preserves the independent
review finding. The frozen contract now explicitly includes `removed_ids`, and
the generated frontend contract matches it. Polling uses these retained tombstone
IDs to erase already-cached bodies after moderation. No IDs are silently truncated.
This intentionally remains a local-pilot limit: the invalidation payload grows
with retained removals in the 72-hour chat window. Before meaningful cloud
traffic, replace it with a bounded invalidation cursor; do not claim this response
is already load-tested or suitable for unrestricted production scale.

The frozen `ChatThread` shape in `docs/backend/Sprint-7.md:132-135` lists `event_id`, `event_title`, `status`, `deletes_at`, `can_send`, `items`, and `next_before`, but not `removed_ids`. The current `Code/Backend/app/domains/chat/schemas.py:22-30` adds `removed_ids`; `Code/Backend/app/domains/chat/service.py:208-224` loads every retained tombstone ID for the event on every page. The frontend generated type and `Code/Frontend/features/communication/ChatWorkspace.tsx:305-402` also consume this extra field. This is a frozen API/schema deviation, and the tombstone query/response grows with retained removals rather than the requested page size. Main should explicitly reconcile the API seam and define bounded tombstone behavior before treating the response contract as complete. I did not edit production, frontend, or generated files.

## Integration seams observed

The current source snapshot includes the social, chat, and moderation routers in the API router; the Sprint 7 models in the migration/model path; pending-person restriction on the actor and event create/publish paths; notification-read support; and deadline-worker calls for report catch-up and chat retention. These seams were inspected, not database-verified. Main owns the shared PostgreSQL suite in its assigned serial slot; the unresolved `ChatThread.removed_ids` contract seam remains for explicit reconciliation.

## Checks and limits

- Python AST parsing of `test_sprint7_quality.py` after the role-isolation correction: passed.
- PostgreSQL integration tests: not run by this QA task; Main reported five passes before the role-isolation test-oracle failure, and the corrected assertion has not been rerun.
- Import smoke check for `app.main`: blocked by the workspace environment's `pydantic` import error (`cannot import name 'BaseModel'`).
- Pytest import check: unavailable in the backend virtual environment (`pytest` is not installed); no dependency was installed.
- Ruff: not present in the backend virtual environment and no Ruff configuration was found in `Code/Backend/pyproject.toml`; lint was not run.
- No production files, migrations, shared registration, router, generated types, or other domains were edited.

## Coordinator verification, 2026-10-15

The earlier environment/test-run limits describe the isolated QA worker, not the
final integrated environment. The coordinator used `.mvp-venv` and the dedicated
PostgreSQL scratch database, with all database tests serial. The complete backend
suite passed: **257 passed, 3 opt-in browser tests skipped, one upstream dependency
deprecation warning**. The corrected role-isolation test and all four source
findings above are covered by passing integrated regression tests. The browser
gates run separately and are recorded in the final acceptance note.

Additional integration fixes preserve same-key comment/chat outcomes under a
new personal restriction, sample write clocks after locking, validate chat event
IDs as UUIDs, and recover an existing report receipt without exposing a newly
hidden target. User metadata locks use `NO KEY UPDATE` so notification foreign-key
checks do not create a cross-event deadlock cycle; existing admission-order tests
still verify the actual server ordering contract. Manual escalation starts its
platform window at the action, while automatic escalation uses the durable
organization deadline. Frontend cached chat removals, report decision labels,
notification labels, polling cleanup and PLM-consistent control styling were also
checked during integration.

Final browser verification also passed: nine Sprint 7 communication/safety groups,
eight Sprint 6 approval/reconfirmation groups, and the ten-group Sprint 5 core
journey/viewport/restart gate. The core gate initially caught social-preview height
regression; related spacing was corrected and the unchanged first-card/artwork
assertions then passed. Nine frontend contract tests, lint, both test-port and
normal-port TypeScript/static builds, credential guards and Alembic drift checks
passed. Exact evidence and the local-only release limits are recorded in
[Sprint 7 acceptance](sprint-7-acceptance-2026-10-15.md).

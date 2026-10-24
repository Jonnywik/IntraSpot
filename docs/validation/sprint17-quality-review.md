# Sprint 17 backend planning quality review

Date: 2026-10-20

## Scope

Added PostgreSQL-backed API regressions in `Code/Backend/tests/planning/test_api.py` and a package initializer to avoid test-module collisions. Reviewed the integrated planning service, event public-read route, and saved-event migration read-only; no owner implementation files were edited.

## Coverage added

- Any authenticated active account can save without registration eligibility; save itself leaves event counters and registrations unchanged.
- Guest, forged, inactive, and cross-account access rejection; user-supplied account IDs cannot cross the caller boundary.
- Draft and pending/rejected-organization visibility guards, including the existing public event detail route.
- Idempotent save/removal, exact one-row and stable timestamp behavior under concurrent requests, and persistence after application recreation.
- Ended public events remain saveable; retained references are redacted when an event becomes unavailable and remain removable. A valid published-to-draft transition is also covered.
- Strict half-open conflict intervals, Manila-offset/UTC equivalence, deterministic order, registration-status and organization exclusions, no personal-data leakage, and no registration/capacity side effects.
- Ended conflicting events and ended conflict targets return no conflicts; all route IDs are UUID-validated.

## Review findings and limits

- The first serial focused run was reported by the coordinator as 10 passing and 3 failing. One failure was the test checking `next_admission` after deliberately submitting an ineligible registration; the assertion is now made immediately after save, before registration intake. The other two were direct public GETs for published events of pending/rejected organizations. The coordinator has since added the approved-organization guard in `Code/Backend/app/domains/events/routes.py`; the regression assertions remain.
- A cancelled *event* cannot currently be represented: `Event.status` is constrained to `draft` or `published` in `Code/Backend/app/domains/events/models.py`, and no event-cancellation state is present in this contract. Registration status `cancelled` is covered as an excluded conflict. The saved-reference redaction test uses the valid `draft` transition; a true cancelled-event redaction case needs an owner-defined event cancellation contract/state.
- At the initial integration snapshot, saved-list projection re-queried each saved event and calculated confirmed/reserved counts per event. The coordinator has taken ownership of batching saved-event public projections and grouped counts. Added a query-count regression with eight saved references (four visible and four unavailable), counting SQL for the full authenticated GET and enforcing a fixed ceiling of eight statements.

## Verification status

Coordinator final verification supersedes the preliminary run below: new planning
tests passed 15/15, the wider regression passed 505 cases (10 historical opt-in
browser gates skipped), and a browser-discovered CORS PUT regression plus foundation
checks passed 10/10. Batched projection/query-bound checks pass. The actual save,
calendar, cross-account isolation, removal and restart journey also passed. See
`docs/validation/sprint-17-acceptance-2026-10-20.md` for complete evidence and limits.

### Historical worker handoff before the coordinator rerun

The coordinator owns the serial PostgreSQL slot. This reviewer did not run any database suite. The coordinator's reported run preceded the latest assertion adjustment and four added regressions (application recreation, mixed-visibility query bound, draft redaction, ended target); those changes remain unverified until the coordinator's next serial run. Python AST parsing, a trailing-whitespace check, and a 100-character line-length check passed for the final scoped files. Ruff was not available on PATH during the earlier check.

The DB row/table baselines were coordinator-reported and were not independently queried by this reviewer. No migrations, seed data, commits, or external services were run by this QA work.

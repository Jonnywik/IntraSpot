# Sprint 23 integrated event-safety review

Review date: 2026-10-24

Frozen contract: [`docs/backend/Sprint-22.md`](../backend/Sprint-22.md)

## Review scope

Reviewed the shared policy and event-safety service, their routes and models, and callers in registration, event discovery/detail, saved-event projections, attendance, featured placement, social content, media, and confirmed chat. The review traced hide-channel separation, 2A admission behavior, terminal state, versions and retries, current authority, lock order, and suspension/report expiry.

## Findings

### Resolved in code: suspension now waits for in-flight event admissions

The source-level reproduction sequence was: registration processing reads `available` at `Code/Backend/app/domains/registrations/service.py:550`; suspension commits before the insert at line 557. Registration holds the event row; suspension previously locked only the organization and suspension row.

`change_organization_suspension` now locks all published event rows for the organization in sorted ID order after obtaining the organization lock and before writing suspension state. This matches the existing event lock held by intake/processing: in-flight admissions finish before suspension commits, and later processing observes the committed restriction. Event creation/publication remains serialized by the organization lock. The deterministic PostgreSQL regression pauses after the availability check, verifies through `pg_stat_activity` that suspension is blocked by that registration transaction, then checks that the in-flight waitlist outcome remains active, a later join is rejected, and FIFO promotion and original receipt replay still work under suspension.

The implementation and regression are coded. The regression is not yet execution-verified because the coordinator owns the serial PostgreSQL slot.

### Fixed: direct requests could hide a draft

The event-safety state reports `can_hide: false` unless the event is published, but the action path previously accepted `hide` for any nonterminal event. A direct hide on a draft could therefore create a safety restriction that later blocks publication. The service now rejects that action, and `tests/quality/test_sprint23_safety.py` covers the API response and absence of a control row/audit.

## Other traced behavior

- Organization and platform hide bits are updated and restored independently.
- The shared policy excludes hidden/suspended events from discovery and rejects fresh admissions after suspension commits. Existing review/deadline/FIFO work continues, and confirmed chat still relies on unchanged confirmed-registration state.
- Terminal removal/cancellation is checked before hide/restore or mutable-event use, and the shared cancellation hook runs after the terminal flag is set.
- Safety replays are reached only after current eligibility/staff/platform authority checks; version and payload conflicts remain enforced.
- Suspension expiry uses the exact `until <= at` boundary, clears the timestamp once, increments the version, and records one system audit/notice. Report expiry clears evidence and records terminal status under the ordered locks.
- Caller checks confirmed saved-event public projections and featured/discovery queries use the shared policy; attendance and social/media writes retain terminal guards.

## Verification limits

Static source review and AST parsing passed for the shared policy, event-safety service, and new regression. The new PostgreSQL regression was not executed because the coordinator owns the serial database run. No database suites, builds, dependency installs, browser tools, or Git operations were run. Existing browser, security, participant, live-identity, and release gates remain open as recorded in the canonical Sprint 22 notes.

## Coordinator execution addendum

The final serial PostgreSQL run passed both new regressions plus all event-safety
domain and Sprint 22 quality cases. The suspension test observed the exact
registration blocker through PostgreSQL lock inspection, then verified later
denial, continued promotion and original replay. Integrated results, focused
live browser evidence and remaining gates are recorded in the
[Sprint 23 acceptance record](sprint-23-acceptance-2026-10-24.md). This addendum
does not attribute the coordinator's executions to the review worker.

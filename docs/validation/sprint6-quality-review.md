# Sprint 6 independent quality review

Review date: 2026-10-13  
Scope: source audit of the Sprint 6 registration, deadline, authorization, privacy, material-change, and attendee/management UI flows. Production code is read-only in this review.

## What this change does

Sprint 6 adds approval-based registration, durable review deadlines and escalation, per-event persona sharing, reconfirmation after material event changes, and capacity-safe seat selection. The current source preserves the exact-selection default and the optional `newest_in_pool` mode, and the attendee UI exposes pending, waitlist, and reconfirmation states.

## Findings

No open QA findings remain in the reviewed Sprint 6 seams.

## Source-verified resolution

The earlier optional recommendation that an extension warning should reach the assigned reviewer is resolved in source. On the first expired review stage, `_catch_up_deadlines_locked` sends the registrant a warning and separately targets `registration.reviewer_id`, with a reviewer-specific dedupe key (`Code/Backend/app/domains/registrations/service.py:573-588`). Coordinator follow-up added assertions for exactly two warning recipients (applicant and assigned owner) to the restart-safe escalation test; the final serial quality/browser run passed all ten tests. QA itself did not run that gate.

The earlier P2 follow-up-tab issue is also resolved in source. `RegistrationAction` routes waitlisted outcomes to `tab=waitlist`, pending/reconfirmation outcomes to `tab=pending`, and other terminal/confirmed outcomes to `tab=confirmed` (`Code/Frontend/features/registrations/RegistrationAction.tsx:189`). `MyEvents` accepts the supported requested tabs, defaults invalid or absent values to confirmed, and keys its content by session version plus validated tab so tab/session changes reset the selected state (`Code/Frontend/features/registrations/MyEvents.tsx:202-215`). The page wraps the search-param-reading client component in Suspense (`Code/Frontend/app/my-events/page.tsx:1-8`).

## Focused source audit

- Queue and decision operations authorize before draining receipts or applying deadline catch-up; the event timestamp is sampled after its row lock (`service.py:694-723`). The QA regression covers an expired cross-organization queue and decision request and asserts `403` with no state or notice changes.
- Deadline catch-up progresses from persisted deadlines, records integer stages, sends a distinct reviewer reminder on the one-time extension, escalates to a different reviewer, and releases reservations at final expiry (`service.py:541-627`).
- Material reconciliation catches up deadlines before calculating holders (`service.py:1010-1020`). Seat occupancy includes confirmed, pending, and reconfirmation-required registrations; selection validation rejects non-holders and duplicate IDs, exact mode requires the precise deficit, and `newest_in_pool` only cancels within the selected pool and rejects nonempty zero-deficit input (`service.py:1041-1081`). The helper also notifies active registrants and organization members with revision-scoped dedupe keys (`service.py:1083-1113`).
- Review rows use the nested `{registration, user_id, persona}` projection. Reviewer authorization is organization-scoped; persona fields are queried only for opted-in registrants before event end and do not include email or image fields (`service.py:731-783`). The frontend consumes the nested registration object and integer `review_stage` (`Code/Frontend/features/organizations/RegistrationReview.tsx:9,100-108`).
- Capacity reduction UI defaults to exact selection, exposes `newest_in_pool` explicitly, counts pending and reconfirmation reservations, and submits only currently selected holder IDs (`Code/Frontend/features/organizations/EventChanges.tsx:66,82-91,131-151,247-280`).

## Verification and handoff

- **Coordinator-reported serial PostgreSQL verification (not run by QA):** QA, infrastructure, and events tests: 55 passed; full regression: 205 passed. All nine QA cases passed in both runs. The runs also reported two browser skips and two upstream warnings.
  - The initial capacity-selector accessible-name failure was corrected with an explicit aria-label and subsequently passed the real browser rerun.
- The owned QA test file passed syntax-only compilation; no test cases were executed by QA.
- QA did not run PostgreSQL tests or reset the shared database. No whole-project frontend build or browser test was run by QA.
  - **Coordinator-reported live Sprint 6 browser gate:** passed one test covering eight journey groups in 18.88 seconds. Main reports the capacity selector was found by its accessible name after the explicit aria-label correction, the pending and waitlist tabs are selected after following View My Events, and the mobile decline flow shows success and terminal cancelled status after save. This is coordinator-reported browser evidence, not a gate executed by QA.
- No production files were edited and no commits were made.

Verdict: the follow-up-tab P2 is resolved in source and covered by the coordinator-reported Sprint 6 browser gate. No reviewed Sprint 6 QA blocker remains.

Coordinator follow-up: the separate Sprint 5 browser gate passed in 49.67 seconds, including ten journey/check groups, five viewport sizes and API restart recovery. This result was not executed by QA. The upstream Starlette/httpx deprecation and Pydantic field-alias warnings remain non-blocking observations; dependency changes are outside this sprint.

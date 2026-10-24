# Sprint 18 — independent quality review

**Date:** 2026-10-23

**Status:** Independent cases prepared by the QA worker; coordinator integrated the
fixes and ran the tests. Live browser acceptance remains pending.

## Added regression coverage

`Code/Backend/tests/quality/test_sprint18_quality.py` adds route/service-boundary checks for:

- Pending approval applicants with globally visible personas: profile lookup remains unavailable, and pending, hidden, blocked and unknown targets share the same unavailable response. Once confirmed, the HTTP persona projection contains only the five approved text fields.
- MembershipReview through its HTTP endpoint: a reviewer/applicant block in either direction masks a separately consented persona, nickname label and tags.
- Shared-chat and persona context expiry at the exact 72-hour retention cutoff, including the final microsecond before expiry.
- Blocking does not delete registrations, organization membership, retained chat/comment content, moderation evidence or notifications.

These complement (rather than repeat) the worker persona tests for basic blocking/visibility and the worker RegistrationReview tests for both block directions.

## Finding — stale persona labels survive remote privacy changes

**[P1] Already-rendered comments/chat messages can keep a nickname label after a block or visibility revocation.** Chat polls every five seconds, but requests use `after_sequence` and merge only returned messages, leaving prior `author_label` values untouched (`Code/Frontend/features/communication/ChatWorkspace.tsx:348-357,385`). Event comments have no periodic content/label refresh; loaded pages retain the labels returned when each page was fetched (`Code/Frontend/features/communication/EventSocial.tsx:114-133`). A local custom event refreshes an open persona panel in the same window, but cannot invalidate another account’s already-rendered labels.

**Minimal existing seam:** add an additive `author_labels` map to `ChatThread` and `ContentPage`, computed server-side from the current event’s authors and current viewer’s authorized persona scope using the existing batch visibility resolver. On chat polls, apply that map to all already-loaded items after merging new messages. For comments, refresh only the label map (or a lightweight first-page response carrying the map) and patch labels by `author_id`; do not replace the loaded comment list or discard older pages. This keeps message/comment bodies, ordering and shared-chat access unchanged while making the server’s current privacy decision authoritative.

## Verification boundary

Coordinator follow-up: the current-label map and client refresh are implemented.
The map excludes removed/locally hidden-only comment authors and chat authors
without current confirmed/unrevoked access; empty incremental polls still refresh
labels for retained content. Local block changes clear cached names immediately;
remote changes refresh on visible chat polls (5 seconds) or comment/profile
refresh (30 seconds/focus). Failure clears labels rather than retaining stale
private names. Bodies and older loaded items are retained. Keyed component
instances prevent cross-account/context flashes and late-request state leaks.
The final focused privacy/warning/migration/contract run passed 32 tests, including
all independent QA cases. See the acceptance record for combined evidence and
remaining browser/dependency gates; no participant validation is claimed.

- Python AST syntax parsing succeeded for the new test module.
- No pytest/DB runtime tests or browser tests were run by this QA pass; PostgreSQL test execution remains with the coordinator and should run serially.
- Coordinator-reported progress: migration passed, five infrastructure tests passed, preservation checks retained 30 tables in each DB, and the registration-warning suite had 12 passing dots so far. These are coordinator reports, not results independently reproduced here.
- Browser verification should confirm old comment/chat labels refresh after the other participant blocks or revokes visibility, while preserving loaded older content and leaving message bodies readable.

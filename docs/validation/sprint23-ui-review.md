# Sprint 23 event-safety UI review

Date: 2026-10-24. Bounded source review and fixes completed; full sprint
acceptance remains open.

## Scope and findings

Compared the current event-safety UI with the frozen Sprint 22 contract and its
generated API schemas. Review covered request-key recovery and scope, queue
loading/selection, report/event versions and deadlines, platform and organization
restoration, native confirmation dialogs, evidence rendering, translations,
theme/high-contrast tokens, and mobile reporting versus desktop management.

Four UI issues were corrected:

1. A 409 response queued a refresh but the warning said the latest data was
   already loaded. The event-control and report-queue feedback now asks the user
   to refresh and review the current state.
2. Queue decision success accepted any report version greater than the captured
   version; a response with a missing version could therefore be treated as
   success and discard the retry key. The response must now advance exactly one
   version and return the exact status for the requested action.
3. While an uncertain queue decision remained pending, selecting another report
   changed the visible details but the retry notice did not identify the original
   target. The retry notice now names the report whose frozen request will be
   resent.
4. The backend can return HTTP 200 with `expired` and the next report version
   after sweeping a due report without applying the requested decision. This now
   clears the pending key, warns in English/Filipino that no decision was saved,
   and uses the existing queued refresh. Only the exact requested action's
   resulting status confirms success; malformed or mismatched responses preserve
   the original retry.

No other reproduced UI defect was found in the reviewed areas. Existing
permission fields remain server-derived; queue decisions retain both captured
versions; evidence is bounded to the five approved snapshot fields and rendered
as text; reporting remains available at mobile widths while management is
desktop-only.

## Verification

- Focused Node run: **14 passed** (10 existing Sprint 22 safety UI checks and 4
  new Sprint 23 review checks).
- Final bounded follow-up: **7 Sprint 23 checks passed**, including behavioral
  coverage for expired responses, every action/status pairing, mismatched IDs or
  versions, and malformed responses. The main thread owns the final full run.
- Scoped ESLint was started, then stopped when the main thread reported that its
  shared lint/type gates were running. No scoped ESLint result is claimed here.
- No browser, database suite, build, install, shared TypeScript check, or Git
  operation was run for this bounded review. The earlier Sprint 22 report's 140
  frontend checks were not rerun as a full suite.

## Acceptance boundary

The canonical Obsidian AI Index still identifies Sprint 22 as current and says
Sprint 23 is planned. This record covers only the explicitly requested UI
review; it does not change that project phase or claim browser, participant,
accessibility-matrix, security, or release acceptance.

## Coordinator execution addendum

The paragraph above records the state at worker review time. The coordinator's
final **147-test** frontend run, whole ESLint/TypeScript checks and both isolated
exports passed after the reviewed fixes. Focused live app checks verified guest,
faculty, owner and platform-admin views without submitting mutations; registration
and reporting dialogs returned focus on Escape. Canonical checkpoint notes are
updated separately. See the [integrated acceptance record](sprint-23-acceptance-2026-10-24.md)
for precise browser limits and release gates; no participant or full matrix pass
is implied.

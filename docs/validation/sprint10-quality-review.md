# Sprint 10 quality review

**Status: developer-only review and actual browser gate passed, 2026-10-16.**
The coordinator ran the serial isolated test: one passed in 67.48 seconds,
covering 18 journey/viewport groups. These are not participant tests. Evidence
is saved under `sprint10-browser-evidence/2026-10-16-final/`.

## Regression coverage authored

- Pending owner draft autosave failure, retained edits, explicit retry, reload,
  publish gate, and declined account-switch discard.
- Browser-back confirmation after opening the draft from a real workspace link;
  dismissing it must keep the editor route, pending-owner session, and unsaved
  title. The check requires the Navigation API on the Microsoft Edge baseline.
- Platform accreditation decision cancellation (no request) followed by
  confirmed approval; approved publish uses `If-Match` and its public response
  omits the private draft version.
- Two-tab stale publish and autosave conflicts, explicit reload, and preservation
  of current edits.
- Inbox status/category filter composition, read feedback, and event/club/chat
  destinations; moderator notification includes both organization and event
  context and loads the organization-scoped review summary.
- Member/staff boundary checks, platform safety destination, desktop fit at
  1280×720, 1366×768, 1440×900, and 1920×1080, plus mobile management checks.
- Default light 1440×900 screenshots for management, draft, admin, and inbox;
  dark, extra-large-text, high-contrast screenshots for draft, admin, inbox, and
  staff workspace. The harness writes these and a sanitized `results.json` to a
  fresh OS temporary directory. Artifacts contain no auth tokens or email
  addresses; screenshot fixtures use fictional accounts and records.

## Findings and disposition

1. **Clarified and exercised — mobile draft creation.** The initial component-only
   inspection missed the page's existing outer desktop-only wrapper; creation
   was already blocked there. Its visible mobile notice is now localized and
   consistent. The editor also hides its create card if reused independently.
   The 390×844 browser check passed.
2. **Fixed and exercised — browser-back protection.** The original inspected
   draft source snapshot had unload, internal-link, and account-change guards,
   but no Navigation API traversal listener. The new Edge regression requires
   traversal interception and retained input; that listener is now in the export
   and the coordinator exercised a dismissed same-origin traversal in Edge.
3. **Compatibility limitation — fallback traversal behavior is not proven.**
   The harness uses Microsoft Edge and exercises its Navigation API path. A
   browser without Navigation API support relies on the native `beforeunload`
   fallback; the harness does not establish that such a browser can preserve the
   SPA draft view or provide the same app-specific dismissal behavior. Supported
   browsers may also make certain traversals noncancelable.
4. **Fixed and exercised — short-summary accessible name.** The original
   markup wraps the changing character counter inside the text label. An
   explicit accessible name is now exactly “Short summary”; the browser's
   exact-label selector successfully edits it through failure/retry/reload.

Coordinator review also corrected the inherited 760 px form cap, moved a selected
workspace's new-application form into a collapsed section, removed a nested main
landmark, preserved moderator feedback while refreshing summaries, and made deep
link scrolling respect the resolved reduced-motion preference. The expanded
Filipino/extra-large browser check found the profile control overflowing at
1280×720. Wrapping the header utility links fixed it; the four-viewport check
then passed. The description field also received an exact accessible label.

The former moderator first-50 discovery concern is addressed in the current
shared implementation with organization-scoped review summaries. The harness
asserts that scoped request and its event-aware destination; that browser journey
passed, including a persisted moderator registration decision.

## Checks and limitations

- `node --check docs/validation/sprint10-browser-check.mjs`: passed after the
  harness changes.
- Pytest `--collect-only`: the coordinator reports one test collected. The
  system Python available to this assessor did not have pytest installed, so
  that collection result is not independently reproduced here.
- Browser execution, frontend build, and database tests were run by the
  coordinator after this assessor's authored checks. The communication/safety
  browser regression also passed nine groups in 26.85 seconds. All database
  suites used the isolated scratch database.
- Backend/frontend test totals mentioned during coordination are reported by
  the coordinator, not independently verified in this review.

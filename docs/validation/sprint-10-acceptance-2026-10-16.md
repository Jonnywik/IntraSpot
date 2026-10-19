# Sprint 10 acceptance — desktop management, autosave and inbox

Status: Sprint 10 complete for the local fictional MVP, 2026-10-16.

## Delivered

- Extended Quiet Heritage desktop management layout to organization selection,
  event lists, member operations, registration decisions, material-change forms,
  accreditation assessment and safety review. A selected workspace now leads;
  applying for another workspace is a collapsed secondary section.
- Added serialized 900 ms draft autosave, visible save/error/conflict states,
  explicit retry and reload, live preview, and incomplete-draft support. Typing
  during a request stays editable. Publishing remains an explicit approved-org
  action with a saved, validated preview.
- Added private content versions and optional quoted `If-Match` checks under the
  event lock for saving and publishing. Stale attempts receive `draft_conflict`
  and do not overwrite or publish newer content. Public results omit versions.
- Added approved-organization staff review summaries with pending counts and
  earliest deadlines. Moderators no longer depend on the limited public feed.
  Existing role/eligibility policy is reused; summaries contain no registrant
  identities or private profile fields.
- Organized the current account's latest 100 notifications with composed
  All/Unread and category filters, counts, per-item read feedback and contextual
  destinations. Event organization context is derived for legacy reads without
  rewriting those rows; new event notices store their organization context.
- Applied English/Filipino copy, independent account preferences, theme/contrast,
  larger text and reduced motion to management. Mobile management stays blocked;
  its outer draft-page notice is now localized and consistent with the editor.

## Review corrections

The coordinator integrated four disjoint Luna/max implementation workers and a
separate Luna/max quality assessor. All agents are closed. Coordinator review
and actual browser execution corrected:

1. An inherited 760 px form cap that constrained the full editor/preview grid.
2. An application form occupying the first screen of a selected workspace and a
   nested main landmark; selected work and readable sidebar labels now lead.
3. React ref/state synchronization and render-time clock issues caught by lint.
4. Inexact summary/description accessible labels and client field limits.
5. Lost moderator result/error feedback while refreshing parent event summaries.
6. Smooth deep-link scrolling despite the resolved reduced-motion preference.
7. The profile control extending beyond 1280 px with Filipino extra-large text;
   utility links now wrap instead of reducing the chosen text size.
8. A mismatch between the outer mobile page notice and the hidden editor notice.
   The page already blocked mobile management; the assessor's initial claim that
   creation was actionable did not account for that outer wrapper. The editor
   also now hides its create card if reused outside the page wrapper.

## Verification

| Check | Actual result |
|---|---|
| Focused draft/precondition and existing event suite | 41 passed |
| Broad PostgreSQL backend regression run | 342 passed, 5 opt-in browser skips, 609.24 s |
| Later staff-summary/notification-context and chat/boundary checks | 25 passed, 35.94 s |
| Frontend API, localization and notification destination contracts | 16 passed |
| ESLint | Passed on final source, including wrapper changes |
| Optimized static export and TypeScript | Passed; 13 static pages generated on host build |
| Public/static credential guards | Passed with optimized exports |
| Alembic schema drift | No new upgrade operations; head remains mvp_0007 |
| Sprint 10 actual browser gate | 1 passed, 18 groups, 67.48 s |
| Existing communication/safety browser regression | 1 passed, 9 groups, 26.85 s |

The broad run preceded the later staff-summary/notification-context changes;
those changes have their own subsequent focused checks. Database suites run
serially against `intraspot_mvp_test`, never the development data. Browser journeys
use an export configured for test API port 8002; the normal optimized export was
restored to API port 8001 afterward. Existing upstream Starlette/httpx deprecation
and Node module-type test warnings are non-blocking and unchanged.

The new harness checks held-save typing, failed-save retry/reload, canceled
account changes and browser back, accreditation cancel/commit, approved publishing,
two-tab conflicts, inbox read/filter behavior, staff/member isolation, responsive
geometry at 1280×720, 1366×768, 1440×900 and 1920×1080, Filipino extra-large copy,
and mobile management restrictions. These are developer-operated browser checks,
not participant validation.

Final evidence: [Sprint 10 results](sprint10-browser-evidence/2026-10-16-final/results.json)
and ten screenshots in the same folder, including default light workspaces,
draft/admin/inbox, and dark/extra-large/high-contrast and Filipino examples.
Communication/safety evidence is saved separately under
`sprint10-browser-evidence/2026-10-16-safety/`; historical Sprint 7 evidence was
not overwritten.

## Environment and preservation

One generated `.next` cache was moved recoverably into ignored
`Code/Frontend/.cache/next-sprint10-recovery-f8b3a0d602a444f3aa7a94e86f0c361a`.
Fresh static export workers also hit sandbox filesystem restrictions; the build
passed outside that process sandbox. Edge likewise required host execution.
No ACL, dependency, database-volume or user-data reset was performed.
The existing local fictional-account catalog was renewed without changing
profiles/privileges, and the 30-second deadline worker was restored.

Final normal-runtime checks: frontend `http://127.0.0.1:3000`, backend readiness,
public upcoming events and the API fictional-account catalog all returned HTTP
200. Readiness reports `mvp_0007`; the live OpenAPI includes the scoped staff
review route, and the served static bundles target development API port 8001.

## Limits and next boundary

- Browser-back confirmation covers cancelable Navigation API traversals in the
  tested Edge baseline. Noncancelable/unsupported SPA traversals are not promised
  the same protection. Native unload/link/account guards remain in place.
- Editing clients that omit the optional `If-Match` header retain legacy behavior;
  future editing integrations must send it for equivalent conflict detection.
- Inbox filters cover the explicitly stated latest-100 window; no new push,
  email, bulk-read or deletion behavior was added.
- No new migration, Penpot synchronization, real sign-in or deployment.
- Sprint 11 mobile attendee closure is next in the accepted roadmap. Participant
  testing and real-user release remain separately deferred.

See [execution contract](../backend/Sprint-10.md),
[interaction handoff](../design/sprint10-interaction-handoff.md), and
[quality review](sprint10-quality-review.md).

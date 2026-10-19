# Sprint 9 acceptance — desktop attendee polish and preferences

Status: Sprint 9 complete for the local fictional MVP (2026-10-16).
Developer verification only. Participant testing remains deferred at the user's
request; no real-user release, cloud integration or Penpot synchronization.

## Delivered

- Selected A / Quiet Heritage expanded to use desktop side space, with existing
  club/route shortcuts left and private upcoming registrations/status right.
  Feed stays single-column and <=680px; workspace <=1440px. Sidebars reflow at
  1180/1000px; mobile still has four labeled tabs.
- Shared PLM colors, serif headings, sans interface, centered button labels,
  consistent controls/statuses, responsive cards, keyboard focus and hover/press
  feedback. Static card hitboxes prevent hover flicker; artwork stays cropped.
- Refined details/registration, My Events, Chat, Profile and Settings. Chat uses
  separate header, message-scroll area and composer without sticky overlap.
- English/Filipino attendee interface; light/dark/system theme; three text sizes;
  high contrast, reduced motion and pausable Discover linework. Organization and
  user-authored text is not translated.
- Private authenticated GET/PATCH preferences, atomic partial PostgreSQL upsert,
  defaults without read-side writes, strict input validation. Guest device
  preferences do not seed accounts. Serialized saves retain retryable intent,
  guard stale responses and isolate accounts. Corrupt guest records can reset.
- Local demo reload restores only a remembered account label after fresh catalog
  retrieval and `/me` verification; tokens are never put in browser storage.
- Explicit additive migration `mvp_0007`, reviewed OpenAPI/generated frontend
  types and readiness tied to the current reviewed migration head.

Six GPT-6 Luna/max workers covered backend preferences, preferences/localization,
events/registration, attendee pages, social/notification copy and independent QA.
The main chat owned shared infrastructure, integration, fixes and final checks.
Workers are closed. No future-sprint feature was added to fill sidebars.

## Verified checkpoints

| Check | Result |
|---|---|
| Full serial PostgreSQL regression suite | 333 passed, 5 opt-in browser gates skipped |
| Additional preference migration/readiness regressions | 3 passed |
| Frontend contract/localization tests | 12 passed |
| ESLint | Passed |
| Static build, TypeScript and public credential guard | Passed, 13 generated static pages |
| Existing Sprint 5–8 persisted browser gates | 4 passed on the polished app |
| Sprint 9 browser preferences/geometry gate | Passed, including ten preference/responsive groups and two geometry/interaction groups |
| Development API `/health` and `/ready` | Local / ready / mvp_0007 |
| Migration metadata drift | Alembic check found no new operations |
| Git whitespace check | Passed |

The full DB suite and three added regressions are separate runs, not a claimed
single 336-test run. DB/browser suites were serialized against guarded
`intraspot_mvp_test` on loopback PostgreSQL 17, never SQLite or Penpot's database.
The browser uses installed Microsoft Edge through bundled Playwright. The static
test build points at isolated API port 8002; normal development is restored to
port 8001 afterward.

Reviewed development migration retained 15 users, 9 organizations, 20 active or
historical memberships, 15 events, 1 registration, 0 receipts and 0 notifications
at its application checkpoint. No fixture domain data was overwritten to apply
preferences. Later normal lifecycle activity can change counts.

Final Sprint 9 evidence:

- `sprint9-browser-evidence/2026-10-16T04-03-51-535Z/results.json`: ten groups,
  no uncaught browser errors; four desktop viewport screenshots, guest and account
  1180/1179/1000/999 breakpoints, mobile four-tab check.
- `sprint9-browser-evidence/2026-10-16T04-03-41-310Z-geometry/results.json`:
  representative first-card fit, hover surface/art movement, stationary hitbox,
  keyboard-visible focus and non-overlapping chat at 1280×720 / 1440×900.
- Serial Sprint 9 runner: 1 passed in 99.26 seconds. The four earlier persisted
  browser gates passed together in the preceding combined run. The intervening
  final corrections remove redundant chat-header margins and compact the demo
  bar/card organization label; no domain rule changed. The final card fixture
  includes a real one-line summary, rather than testing only an empty summary.

One isolated corrupt-storage setup timed out during an earlier run. Diagnostic
capture was added; the final clean run passed without relaxing the readiness
assertion. Treat that timeout as a harness/runtime observation, not proof of a
diagnosed production defect. Earlier failures are retained as diagnostic history.

## Issues found and resolved

- New migration initially exposed an obsolete hard-coded readiness revision;
  readiness now uses the reviewed Alembic head and has a downgrade/readiness test.
- Initial guest state could flash before local account restoration; authentication
  starts loading and preferences wait for verification.
- English could fall through to Filipino-only dictionaries; fallback now respects
  the chosen language. Static coverage and placeholder checks pass.
- Reset could fail to recover corrupt guest storage; explicit reset now replaces
  it with a complete valid record.
- Universal reduced-motion transform removal broke the positioned Clear button;
  static positioning is retained while motion transforms alone are removed.
- Hover lift moved an interactive target; only the card background now lifts.
- Representative first card exceeded the primary viewport; related spacing was
  tightened without reducing text size or artwork aspect ratio.
- Short-desktop chat composer obscured the header; flex layout and contained
  scrolling now separate header, log and composer. Geometry checks include
  overlap, not just action visibility.
- Dark tab-count foreground was too low-contrast; it uses the semantic ink token.

Browser harness corrections preserve, rather than relax, coverage: semantic
definition-list counts, renamed confirmation text, count-bearing tabs, async
attendance refresh, locale-independent settings controls, keyboard modality,
null-safe document observers, genuine same-document stale-response checks and
exclusion of Next's empty route-announcer alert. Early failed screenshot folders
are diagnostic history, not the acceptance baseline.

A repeated Windows/OneDrive generated-cache unlink failure was isolated without
changing production behavior. The generated `.next` directory was moved into
ignored `Code/Frontend/.cache/next-sprint9-recovery-20261016`; source and data were
preserved, and a clean build passed. ESLint excludes that generated cache.

## Handoff limits

See [interaction specification](../design/sprint9-interaction-handoff.md) and
[frozen Sprint 9 contract](../backend/Sprint-9.md). Opening sheet motion and
hover/pause/reduced-motion feedback are implemented; reverse closing animation
and spring settling are not claimed. Targeted contrast/keyboard checks are not
accessibility certification or a professional translation assessment.

Desktop organization/platform workflow polish is Sprint 10; dedicated mobile
closure is Sprint 11. No additional sprint, deployment or real-user pilot was
executed. Changes remain local and uncommitted until requested.

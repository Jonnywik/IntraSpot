# Sprint 11 — mobile attendee completion

Authorized by the user on 2026-10-17. Preserve the completed Sprint 9/10 work,
fictional local identities and existing domain APIs. No deployment or commit.

## Frozen scope

- Preserve PLM Quiet Heritage styling, single-column image-led feed, navy actions,
  burgundy identity and gold focus. Refine, do not redesign or add product modes.
- Exactly four persistent labeled mobile destinations: Discover, My Events, Chat,
  Settings. Profile and Notifications stay in header utilities. No mobile staff
  management, fifth tab or archive tab. All existing roles use attendee mobile UI.
- Discovery search and My Clubs compose under existing eligibility/membership
  rules. Detail counts distinguish attendance, remaining seats and reactions.
- Registration retains explicit confirmation, idempotency and server outcomes;
  show waitlist position/no estimated wait immediately and in My Events. Confirmed
  attendance alone grants chat. Preserve pending/reconfirmation/withdrawal rules.
- Mobile chat opens a focused thread with a real route back to the existing inbox,
  preserving polling/retry keys, archived read-only status and deletion countdown.
  Keep input reachable when the visible viewport shrinks; no simulated backend.
- Profile, inbox and Settings remain reachable, readable and privacy-preserving.
  Keep existing account/guest preference persistence and English/Filipino copy.
- Fit 320, 360, 390 and 430 px widths and short/landscape viewports. Allow vertical
  scrolling; do not hide meaningful content or reduce the chosen text-size setting.
  Touch targets at least 44 px (48 px primary actions), safe-area clearance,
  visible keyboard focus, semantic controls and reduced-motion feedback.
- No Sprint 12 recommendations, flash events, new media, calendar/saved events,
  new auth, management, database migrations or API-policy changes.

## Ownership

Coordinator: shared mobile shell/navigation/foundations, My Events, inbox,
integration, shared messages and contract tests, final verification/handoff.
Independent Luna/max workers: (1) discovery/detail/registration; (2) chat and
communication CSS; (3) Profile/Settings; (4) isolated mobile browser-check harness.
Workers edit only their assigned files and request shared changes.

## Acceptance

Run Node contracts, localization, lint, TypeScript/static export; actual mobile
browser journeys against isolated PostgreSQL for guest search, eligible/faculty
registration, full-event waitlist, profile completion, My Events, chat send/retry,
archive and denial, inbox, independent preferences and desktop-only management.
Check 320/360/390/430 widths, short viewport, English/Filipino, dark/high contrast,
extra-large text, reduced motion and desktop regression. Record screenshots and
actual coverage separately from deferred participant/device testing. Restore
normal local frontend/backend after isolated checks. Never reset development data.

## Result — 2026-10-17

Complete locally. PostgreSQL regression: 166 passed. Frontend contracts and
localization: 27 passed. Lint, TypeScript/static export and credential guards
passed. Actual mobile gate: 11 groups, 54.06 seconds. Final desktop plus
communication/safety browser regressions: 18 + 9 groups, two tests, 85.51 seconds.
No migration, real authentication, deployment, commit or Penpot synchronization.
Participant/native-device testing remains deferred. Sprint 12 is next, not run.
See [acceptance evidence](../validation/sprint-11-acceptance-2026-10-17.md).

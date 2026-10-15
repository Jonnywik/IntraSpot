# Sprint 5 — local frontend integration

Completed local integration gate on 2026-10-13. See
[acceptance and handoff](../validation/sprint-5-acceptance-2026-10-13.md).

Authorized 2026-10-13 after Sprint 4 passed 173 PostgreSQL checks.
Integrate the existing Next.js client with `/api/v1`; no new domain rules,
Penpot changes, cloud connections, real identities or deployment.

## Frozen frontend seams

- Generated OpenAPI types: `lib/api.generated.ts`. Named domain aliases live
  in coordinator-owned `lib/types.ts`.
- `api<T>(path, {token?, method?, body?, idempotencyKey?, signal?})` in
  `lib/api.ts`. Paths are relative to `/api/v1`. Throws `ApiError` with
  `status`, `code`, `message`. Do not log credentials or bodies.
- `useApiResource<T>(path: string|null, token?: string|null)` returns
  `{data, loading, error, reload}`. Null path disables requests. Account
  changes cancel/clear stale private data.
- `useSession()` returns `{actor, token, label, authLoading, error,
  selectAccount(account), signOut(), refreshActor(), version}`. Accounts are
  `{label, token}` fixed fictional credentials, held in memory only.
- `localDemoEnabled()` requires an explicit build flag plus loopback browser
  hostname. The fixture account catalog is served only by the local backend;
  it is never copied into frontend public files or static output.
- Shared feedback component: `Feedback({loading?, error?, onRetry?, children?})`.
- Dates: `formatDate`/`formatTime` use Asia/Manila; authoring inputs convert
  Manila wall time explicitly into UTC before API writes.
- Main layout owns the session provider, desktop header and four-tab mobile
  navigation. Features render only their page content. All forms use existing
  shared CSS classes: page-heading, panel, field, button, button-secondary,
  tabs, status-chip, muted, stack, actions, feed, event-card.

## Non-overlapping Luna/max assignments

| Worker | Exclusive files |
|---|---|
| Identity | `features/identity/*`, `app/profile/page.tsx`, `app/settings/page.tsx` |
| Organizations | `features/organizations/*`, `app/workspace/page.tsx`, `app/admin/page.tsx` |
| Events | `features/events/*`, `app/page.tsx`, `app/events/page.tsx`, `app/draft/page.tsx`, `app/event-artwork.tsx` |
| Registrations | `features/registrations/*`, `app/my-events/page.tsx` |
| Quality assessor | `tests/sprint5-contract.test.mjs`, independent report; shared changes requested |

The coordinator owns all shared files, generated types, CSS, routing configuration,
fixture transport, notifications, browser acceptance and integration. No worker
runs PostgreSQL resets or whole-project build while parallel edits are underway.
The tool has no separate fast-mode control; none is claimed.

## Cross-feature components

Events imports `RegistrationAction({event: PublicEvent})` from
`features/registrations/RegistrationAction`. Registrations provides a confirmation
sheet, immutable retry key during an attempt, immediate outcome and View My Events.
Event details use `/events?eventId=…`; authoring uses
`/draft?orgId=…&eventId=…` (eventId optional). Organizations links these routes;
Events owns draft creation/editing/preview/publishing. Management is desktop-only.

## Acceptance

Guest browsing; eligible attendee profile/registration/waitlist/My Events;
pending owner application/draft/preview; approved publishing; actual platform
admin decision. All results come from persisted FastAPI data, not static outcomes.
Verify loading, empty, validation, forbidden, retry and success states; disable
unsupported features honestly. No static generated event paths, browser database
access or fixture credentials in static output. Preserve approved PLM styling,
single-column feed and four mobile tabs. Participant/security gates remain closed.

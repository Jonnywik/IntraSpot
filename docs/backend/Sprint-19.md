# Sprint 19 — Featured-event requests and decisions

## Approved scope

Implement featured requests, platform approval/rejection/revocation, and a public
Featured badge within normal feed order. Do not build Sprint 18, change rankings,
add spotlight positions, deploy, or synchronize Penpot. Existing mobile navigation,
registration, privacy and accreditation rules remain unchanged.

User decision, 2026-10-22: a material date/time, venue, banner/graphic, capacity or
cost change pauses a pending/approved request and requires fresh platform review.
Other edits do not pause it. Published banner edits remain unsupported under the
existing media policy; do not introduce a new banner-edit workflow.

## Frozen integration contract

- Eligible active organization owners/admins request for their own published,
  approved-organization, not-yet-started event. Platform staff alone decide.
- Repeated requests while pending/paused/approved return the existing request.
  Terminal rejected/revoked/expired requests remain historical; a later request is
  allowed while the event is still eligible. No extra application notes.
- States: pending, paused, approved, rejected, revoked; expired is an effective
  read state at event start, or the end of an approved placement. Reads never
  mutate data. Paused requests are reviewed directly; no automatic reinstatement.
- One platform-wide placement at a time. Approval chooses a UTC-aware half-open
  window `[starts_at, ends_at)` ending no later than event start. Omitted/null
  starts_at means now; explicit starts_at cannot be in the past. No other
  prominence option: this sprint is badge-only. Future non-overlapping windows
  may be approved. PostgreSQL must reject overlaps, including concurrent writes.
- Material fingerprints contain only starts_at, ends_at, venue_name,
  venue_address, banner_key, banner_media_id, capacity, cost_label. Effective
  Featured also requires a current fingerprint match, published event and
  approved organization; expiry is enforced on reads even after a restart.
- Mutations lock organization then event then request, recheck current authority,
  and use a transaction-wide global placement advisory lock for scheduling.
  Existing event material-change flow already holds its event lock; pause in the
  same transaction without acquiring an organization lock. No notifications or
  registration changes are introduced.

### Database (coordinator migration mvp_0013, parent mvp_0012)

`featured_requests`: id String(36) PK, event_id FK events, requested_by FK users,
requested_at UTC, status String(16), version Integer >0, snapshot_hash String(64),
starts_at UTC nullable, ends_at UTC nullable. Partial unique event_id for statuses
pending/paused/approved. Approved rows require a valid non-null window. A partial
GiST exclusion on tstzrange(starts_at, ends_at, '[)') for approved rows prohibits
overlaps without installing an extension.

`featured_decisions`: id String(36) PK, request_id FK featured_requests,
actor_id FK users, action String(16) in requested/approved/rejected/revoked/paused,
created_at UTC, snapshot_hash String(64), starts_at/ends_at UTC nullable.
Append-only application audit; derive actors/time server-side. Index request_id.
Downgrade refuses populated feature tables rather than discarding history.

### API (all paths relative to /api/v1)

- POST /events/{event_id}/featured-requests — no body, returns FeaturedRequestOut.
- GET /organizations/{org_id}/featured-requests — authorized manager history.
- GET /platform-admin/featured-requests — platform review/history (bounded 100).
- POST /platform-admin/featured-requests/{request_id}/decisions — strict body:
  `{action: 'approve'|'reject'|'revoke', version: positive integer,
  starts_at?: aware datetime|null, ends_at?: aware datetime|null}`.
  Approval needs ends_at; other actions reject scheduling fields. Returns updated
  FeaturedRequestOut. Stale versions and overlapping schedules produce 409.
- FeaturedRequestOut: id, event_id, requested_by, requested_at, status (including
  effective expired), version, starts_at, ends_at, event: EventPublic,
  decisions: list[FeaturedDecisionOut].
- FeaturedDecisionOut: id, actor_id, action, created_at, starts_at, ends_at.
- EventPublic adds `is_featured: bool = false`. Populate all public projections,
  including Saved/My Events. Batch feed lookups; do not alter sorting/pagination
  or introduce per-card feature queries. Do not expose audit/request IDs publicly.
- Service seams: `active_featured_event_ids(db, events, at=None) -> set[str]`,
  `pause_for_material_change(db, event, actor_id)`; coordinator integrates them.

### Frontend worker interface

New files only under features/featured plus tests/sprint19-featured-ui.test.mjs.
Export FeaturedRequestControl({eventId, token}) and FeaturedAdminQueue({token})
from `features/featured/FeaturedControls.tsx`; token is string. Export
FeaturedBadge() from `features/featured/FeaturedBadge.tsx`. Types use local
FeaturedRequest/FeaturedDecision aliases in features/featured/types.ts, derived
from generated schema once available; no hand-edits to generated API code.
Export featuredMessages from features/featured/messages.ts (Filipino dictionary).
Coordinator mounts controls in approved manager workspace/event cards, admin
queue in existing desktop platform page, badges on existing event surfaces, and
wires dictionary/types/test scripts. Do not redesign shells or add mobile tabs.

## Acceptance

Prove authority/isolation, duplicate/stale requests, approval/rejection/revocation,
half-open time boundaries, one global placement under concurrency, material
pause/reapproval, non-material stability, expiry/restart safety, unchanged feed
ordering, and public badge privacy. Run database suites serially on isolated test
PostgreSQL. Review additive migration and preserve existing development rows.
Verify loading/error/empty/retry/conflict feedback, focused browser journeys and
desktop/mobile badge fit. Distinguish tests from participant validation.

## Execution status

Complete locally, 2026-10-22. See
`docs/validation/sprint-19-acceptance-2026-10-22.md` for actual checks and limits.
The user selected Sprint 19 directly; Sprint 18 remains unbuilt. No release claim.

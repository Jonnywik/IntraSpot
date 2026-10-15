# Sprint 6 — approval registration and material changes

**Completed local acceptance (2026-10-13):** 205 PostgreSQL regression tests,
both opt-in real-browser gates, nine frontend contract tests, build/lint/static
credential scans and migration checks passed. Final focused quality/browser run:
10 passed. See [Sprint 6 acceptance](../validation/sprint-6-acceptance-2026-10-13.md).
This is not participant validation or real-user release approval.

Authorized 2026-10-13. Local fictional MVP only; no cloud, email, chat,
membership lifecycle, deployment, or Penpot modifications. Sprint 5 remains
the regression baseline. Canonical Functionality and Security & Operations
own review/escalation/reconfirmation/privacy rules. The user's latest decision
resolves capacity reduction: **exact selection is the default**, with an explicit
`newest_in_pool` alternative. Never cancel outside the submitted selection.
Canonical Obsidian notes remain outside the writable workspace; this records
the decision for synchronization, not a replacement source of truth.

## Frozen integration contract

- Event: `registration_mode: instant | approval`; `review_window_minutes`
  is nullable for instant, required in [15,2880] for approval. Drafts may be
  incomplete; publication validates the window and future start. Add
  `material_revision` integer default 0. Existing events remain instant.
- Public/private projections include mode, review window, revision and
  `reserved_count` (pending + reconfirmation_required). Remaining spots subtract
  confirmed + reserved. Interest remains independent. Public reads stay read-only.
- Registration active statuses: confirmed, waitlisted, pending,
  reconfirmation_required. Terminal statuses: cancelled, rejected.
- Add nullable review deadline/stage/reviewer/first-reviewer fields, integer
  timeout_count default 0, boolean from_waitlist and persona_shared default false,
  nullable reconfirm_deadline and reconfirm_revision. Add them as optional/default
  fields to result schemas so old stored idempotent outcomes remain valid.
- Receipt persists `persona_shared` boolean default false. POST registration
  accepts optional JSON `{persona_shared:false}`; same-key incompatible opt-in
  is conflict. No application note or browser eligibility flag.
- Approval submission with available capacity enters pending, reserves one seat,
  and sets initial deadline. Full submissions waitlist without review. Persisted
  admission order remains authoritative. Active duplicates do not allocate again.
- Reviewer authorization: active eligible owner/admin/moderator of the event's
  approved organization, checked server-side. Deterministic assignment by role
  (owner, admin, moderator) then ID is an implementation detail, not a new role.
  Escalated decisions exclude the initial assigned reviewer. If no second
  reviewer exists, preserve the final deadline and release on expiry; never
  silently approve or widen privileges.
- Initial expiry warns once and extends once; extension expiry escalates to a
  different reviewer; final expiry releases the reservation. Calculate follow-on
  deadlines from persisted deadlines, not catch-up time, capped before start.
  Waitlist-origin timeout requeues once with a new durable admission order; a
  second completed timeout cycle removes it. Rejection removes immediately.
- Reviewer projection always omits email/images. Persona fields (nickname,
  age_bracket, tags, pronouns, icebreaker) appear only with per-event opt-in and
  before event end. Global persona visibility is not event consent.
- `GET /events/{id}/registration-review`: authorized staff-only queue/occupied
  registrations, response `list[RegistrationReview]`; opaque user IDs, no emails.
- `POST /events/{id}/registrations/{registration_id}/decision` accepts
  `{decision:approve|reject}`; response RegistrationResult. Reject stale/expired
  and cross-event decisions. Repeated identical terminal decision is safe.
- `POST /events/{id}/registrations/me/reconfirmation` accepts
  `{accept:boolean, revision:int}`; response RegistrationResult. Reject stale
  revisions; accept only current outstanding request before deadline.
- `POST /events/{id}/changes`: owner/admin only, event row locked; accepts optional
  starts_at, ends_at, venue_name, venue_address, capacity, cost_label, required
  reconfirm_deadline, optional `selection_mode:exact|newest_in_pool` default exact,
  and `selected_registration_ids:list[UUID]` default empty. Material changes only;
  no mode changes. Validate full proposed event and deadline before mutating.
- Exact selection must contain exactly the seat deficit; pool must contain at
  least that many valid current seat holders; choose reverse confirmed_at then
  admission order then ID (pending uses admission time). Reject duplicate,
  foreign, inactive, unnecessary selections. Include pending reservations when
  calculating occupied capacity. Never cancel beyond the minimum deficit.
- Material change cancels selected seats, increments revision, puts remaining
  confirmed/reconfirming users in reconfirmation_required with reserved seats,
  and sends durable deduped in-app notices. Pending review deadlines are capped
  to the new event start. Decline/expiry cancels and promotes safely. A second
  change invalidates previous reconfirmation revision.

## Cross-domain seams

Registrations owns `catch_up_event(event_id)`, `catch_up_locked(db,event,at=None)`,
`reconcile_material_change(db,event,fields,reconfirm_deadline,selection_mode,
selected_registration_ids)`; caller holds event lock and transaction. It owns
all capacity/registration changes and review schemas/routes. Events calls the
material helper after manager validation and full proposed event validation,
before applying material fields and incrementing revision; helper uses
`event.material_revision + 1`. All state/notices commit atomically.

Coordinator supplies `app.notifications.notify_in_app(db, *, user_id,event_id,
registration_id=None,kind,message,dedupe_key)` and an explicit deadline worker
CLI `python -m app.deadlines --once` (also bounded polling mode). Deadline reads
and writes trigger catch-up where appropriate; public discovery never mutates.
No migration at API startup. Coordinator owns migrations mvp_0003 (expansion) and
mvp_0004 (approval event integrity), shared router,
configuration, generated API types, fixtures, notification infrastructure,
deadline worker, browser acceptance and full serial PostgreSQL tests.

## Non-overlapping workers

1. Registrations backend: domain registrations + own tests; atomic queue/review,
   catch-up/material helper/reconfirmation/privacy/idempotency.
2. Events backend: domain events + own tests; approval settings, projections,
   authorized material change endpoint; do not edit Registrations.
3. Management frontend: DraftEditor, organization workspace, new review/change
   components; desktop-only. No shared files or attendee components.
4. Attendee frontend: RegistrationAction, MyEvents, EventDetail/DiscoverFeed;
   opt-in, pending/outcomes/reconfirmation/reserved counts. No DraftEditor.
5. QA: independent shared Sprint 6 tests and review report. Do not modify workers'
   files while they are active; request fixes. Do not run shared PG resets in
   parallel; coordinator owns test scheduling. Luna/max; no separate fast control
   exists in the tool, so none is claimed.

## Exit gate

Existing instant journeys pass; approval/pending/waitlist/approve/reject work;
deadlines catch up after restart without repeated notices or duplicate promotions;
capacity safe under concurrent submissions/decisions/changes; exact and pool
selection tested with protected unselected users; opt-in isolation, moderator and
cross-org authorization, stale revision/deadline rejection; desktop management
and mobile attendee flows tested live. Migration/schema/OpenAPI/build/lint checks
pass. Participant testing and security/release review remain required.

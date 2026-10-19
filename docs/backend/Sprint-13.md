# Sprint 13 — Flash events

Authorized 2026-10-18: next approved roadmap sprint. Preserve the current PLM
desktop/mobile layouts, all prior data and existing registration/privacy rules.
User confirmed a saved Show Flash events switch, default on, discovery-only.
No notification muting, per-event hiding, cloud, GPS, calendar, media upload,
announcements, deployment, Penpot changes or commit/push.

## Frozen contracts

- Event type: `event_type: 'scheduled'|'flash'`, default scheduled for old clients,
  added to public/private event projections. Existing database field is reused.
  Incomplete drafts stay supported. Flash drafts must use instant registration
  and no review window; invalid combined writes are rejected, not silently fixed.
  The UI type selector sends the explicit instant/null combination when changing
  to Flash. Scheduled authoring and approval flows are unchanged.
- Flash publishing requires all existing required fields plus
  `published_at < starts_at <= published_at + 24 hours`. Use one server timestamp
  for validation and publication. End must follow start; no new duration limit.
  Coarse area and tags remain optional. Published type/metadata stays immutable.
  Material rescheduling of Flash must remain inside its ORIGINAL publication
  window; no re-publication or boost renewal is added.
- For You rank, BEFORE pagination: eligible active club group, active matching-area
  Flash boost, distinct interest count, exact area, whole-event availability,
  start/ID. A non-club Flash never crosses the club group. Explicit Upcoming and
  Newest are unchanged. Guest For You remains Upcoming with no personal reasons.
- Boost requires a published Flash, nonblank exact normalized chosen area, and
  `published_at <= request_now < published_at + 3 hours` AND `request_now < starts_at`.
  Boundaries are strict at expiry/start. Use the same request clock as discovery.
  No area inference, coordinates, distances or persistent boost flag/worker.
  Poll visible signed-in For You discovery every 30 seconds with existing helper;
  server results are exact, displayed labels may refresh up to 30 seconds later.
- Controlled matched reasons add `flash` in order club/flash/interests/area/
  availability; never echo private input. The existing helper's four positional
  scores remain compatible; append optional Flash score/timestamp arguments.
  Flash event type badge is separate from transient priority and Featured.
- Discovery adds `include_flash: bool = true` query, composing with search, My
  Clubs, all sorts and pagination. False filters BEFORE pagination. Old callers
  still see all published types. This only changes discovery, not detail links,
  registration permission, My Events, chat, counts, or notifications.
- Existing `/me/preferences` adds strict boolean `show_flash`, default true.
  Partial writes preserve every omitted preference. Existing guest preference
  records and mixed-version responses without this field decode as true; a
  malformed present value is rejected. Signed-in choice persists per account;
  guest choice stays on device with the existing preference mechanism. Account
  switching must not copy the guest or another account's choice. The discovery
  switch is disabled until preference scope is ready. Existing reset restores
  defaults, including show_flash=true; private area/windows remain separate.
- Explicit migration `mvp_0009` expands type constraints and adds preference
  column. Guard Flash instant/no-review and published 24h window in DB too.
  Preserve all old rows. Downgrade refuses any Flash row or non-default hidden
  Flash preference instead of destroying new state. Never migrate at startup.

## Ownership and execution

Coordinator owns shared models, migration, legacy expected-head updates, OpenAPI
and generated types, central translations, fixtures, integration, serial DB
verification, local runtime and canonical-note handoff. Four Luna/max workers:
Events backend; event frontend; preference backend/frontend; independent browser
and cross-domain QA. Each owns disjoint files. Request shared changes.

DB tests run serially ONLY on `intraspot_mvp_test`. Preserve development DB and
all uncommitted Sprint 9–12 work. Use real PostgreSQL, not SQLite substitutes.

## Acceptance / stop condition

Prove draft/type validation, pending publish denial, approved Flash publish,
exact 24h/3h/start boundaries, original-window reschedule, no-area/no-match/
expired fallback, club priority, all-sort/search/My Clubs composition, filter
before >50-row pagination, controlled reasons and public draft privacy.
Prove private show_flash default/partial update/strictness/account separation,
legacy guest decoding and migration preservation/guarded downgrade.
Register and waitlist/cancel/promote a Flash event through existing real APIs;
hide it from discovery and confirm My Events/detail/chat access stay unchanged.
Run focused and broad regressions, generated contract checks, localization,
lint/build/credential guards, and actual Edge desktop/mobile English/Filipino XL
journeys. Record exact developer evidence and limits, restore frontend3000/API8001
and existing deadline worker, update handoff. Stop before Sprint 14.

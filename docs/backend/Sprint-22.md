# Sprint 22 — event reports, takedowns and temporary suspension

Frozen contract 2026-10-24. User clarified: organization reviewers may dismiss
reports or temporarily hide their own event; platform staff handle permanent
removal and suspension. Existing approval reviews and FIFO waitlist promotion
continue during hide/suspension; only NEW registration/waitlist admissions stop.
No paused/rebased deadlines. Existing confirmed chat/participation stays usable.

## Authority and lifecycle

Eligible active same-org owner/admin/moderator reviews organization-stage event
reports and sets/restores only the organization hide. Platform admin (current
server privilege, not metadata) reviews platform-stage reports and sets/restores
only the platform hide, permanently removes events, or suspends organizations.
These independent hide channels never clear one another. Suspension expiry/early
restoration never clears either hide or a terminal removal/cancellation.
Owner/admin can cancel their published event, not moderators/platform role alone.
Cancelled/removed events are terminal; no resurrection API or physical deletion.

An event report alone never hides. Initial stage organization, seven-day review
window (reuse existing safety timing); deadline expiry closes report and erases
snapshot evidence without changing event visibility. After the first org report
decision, three DISTINCT reporters' reports created after that decision and
within a rolling seven-day window route the new report to platform review,
fourteen-day window. Count distinct accounts, not keys/duplicate submissions.
An active duplicate reporter/event returns the existing receipt; exact request
retries return stored original results. No automatic hide or suspension.
Reasons: safety, deception. No free text, personal reporting, attachments or
public reporter list. Eligible signed-in PLM users can report an event they can
currently read; guests cannot. No new arbitrary persona/email disclosure.

Hides/suspension exclude events from discovery/search/My Clubs/Featured public
badges and private saved-event public projections. New admissions are denied even
through direct links, after acquiring the event lock and before outcome creation.
Existing receipt retries preserve original outcomes; fresh attempts cannot bypass
the restriction. Existing active participants and eligible org staff may continue
reading hidden/suspended event details, while guests/new outsiders get 404.
Existing reviews, reconfirmation, withdrawals, FIFO promotion and confirmed chat
continue unchanged. Removed/cancelled events deny public detail/social writes,
publishing/material edits and new attendance writes. Preserve staff history.

Removal/cancellation atomically cancels confirmed/waitlisted/pending/reconfirmation
registrations, clears their review fields, seals unprocessed intake outcomes,
and sends deduplicated in-app notices to affected registrants/org members. Do not
promote seats for a terminal event. Keep registration/attendance/audit rows and
original completed receipt outcomes, no physical content/data deletion.

Suspend 1–30 whole days, default 7; store timezone-aware expiry, is_suspended is
authoritative `until > now`, exact boundary. Current platform admin may restore
early. Reads relevant to public discovery/detail and authorized suspension state
run bounded durable expiry catch-up BEFORE acquiring event locks. Each expiry
seals state, increments version and writes one system audit/notice under org lock.
Expiry semantics remain safe after restart/repeated catch-up. No external email.

## New domain models — eventsafety (coordinator owns migration)

- EventControl / event_controls: event_id String36 PK/FK events; org_hidden,
  platform_hidden, removed, cancelled booleans false/server false; version int0
  check `ck_event_controls_version` >=0; org_reviewed_at UTC nullable.
- OrganizationSuspension / organization_suspensions: org_id String36 PK/FK;
  suspended_until UTC nullable; version int0 check `ck_organization_suspensions_version` >=0.
- EventReport / event_reports: id String36 PK; event_id/org_id/reporter_id FKs;
  reason String16 safety/deception; stage String16 organization/platform; status
  String16 open/escalated/dismissed/hidden/removed/upheld/expired; version int1>0;
  evidence Text nullable (JSON text bounded event title/summary/description/venue,
  no private identities); created_at/deadline UTC nonnull, resolved_at nullable.
  Checks ck_event_reports_reason/stage/status/version; unique partial index
  uq_event_reports_active_reporter on reporter_id,event_id WHERE status IN
  ('open','escalated'); ix_event_reports_event_created(event_id,created_at).
- SafetyAudit / safety_audits: id String36 PK; org_id FK nonnull, event_id/report_id
  nullable FKs; actor_id nullable FK users; client_key String100 nullable;
  payload_hash String64 nullable; scope String16 report/event/organization;
  action String16 report/dismiss/hide/restore/remove/uphold/cancel/suspend/resume/expire;
  version int>=0; previous JSONB nonnull; result JSONB nonnull; created_at UTC.
  Unique(actor_id,client_key) uq_safety_audits_actor_key; checks
  ck_safety_audits_scope/action/version; ix_safety_audits_org_created(org_id,created_at).
  This immutable action log also stores original idempotent command outcomes.

All commands have UUID client_key, canonical payload hash including path/action/
captured versions; same actor/key exact retries have no new effects. Incompatible
reuse409. Authority is rechecked before privileged replay. Lock advisory key,
organization, event, report/registrations in that order. Demotions/ownership changes
already serialize org. Do not acquire org locks while holding event locks.

## API /api/v1, strict inputs / frozen output names

POST /events/{event_id}/event-reports {reason,client_key} ->201 EventReportReceipt:
id,event_id,org_id,status,stage,version,deadline. GET /me/event-reports ->latest100
own receipts. GET /moderation/event-reports?org_id=... ->latest100 stage-authorized
EventReportReview: receipt + reason,evidence (bounded escaped text only while
active and before deadline),reporter_id,created_at,event_version,decisions list
SafetyAuditOut. Without org_id require platformadmin and platform-stage only.
POST /moderation/event-reports/{report_id}/decision:
{action:dismiss|hide|remove|uphold,version:StrictInt>=1,event_version:StrictInt>=0,
client_key} -> EventReportReview. Org actions dismiss/hide; platform supports all.
Match captured report AND event versions before a new decision. No stale reversal.
The review `event_version` is an opaque current token: material revision plus
the monotonic safety-control version. A new hide, restoration or material edit
invalidates an older review; refreshing obtains the current token. Snapshot
evidence remains the submitted public content, clearly timestamped.

GET /events/{event_id}/safety -> EventSafetyOut: event_id,org_id,org_hidden,
platform_hidden,removed,cancelled,version,registration_available,can_hide,
can_restore,can_remove,can_cancel (server-derived permissions). Staff/platform only.
POST same path {action:hide|restore|remove|cancel,version>=0,client_key}
->EventSafetyOut. Role chooses independent hide channel. No terminal restoration.

GET /organizations/{org_id}/suspension -> SuspensionOut: org_id,version,
suspended_until,is_suspended,can_manage. Current staff/platform only.
POST same path {action:suspend|resume,version>=0,days:StrictInt1..30|null (default7
for suspend, must null for resume),client_key} ->SuspensionOut. Platform only.
GET /organizations/{org_id}/safety-history ->latest100 SafetyAuditOut for current
staff/platform: id,org_id,event_id,report_id,actor_id,scope,action,version,created_at.
Do NOT expose payload hashes/keys/result/previous snapshots via history DTO.

Backend exports: EventControl,OrganizationSuspension,EventReport,SafetyAudit;
router; service.sweep_expired_suspensions(db,org_id=None,at=None), read/write
services. On removal/cancel call coordinator hook
registrations.service.cancel_event_participation_locked(db,event,action_id).
Catch-up report evidence expiry may be done in safety reads/mutations under proper
locks, no visibility changes and no email. Coordinator owns shared policy below.

## Shared integration ownership

Coordinator: app/core/event_safety.py policy, migration mvp_0017 after0016,
Events routes/projection, Registrations, Attendance, router/models/OpenAPI/types,
frontend parent mounts/i18n/package, notifications routing, migration tests and
serial DB execution. Policy exports:
discovery_clause(at=None) SQL predicate correlated to Event;
event_is_terminal(db,event); registration_is_available(db,event,at=None);
require_new_registration(db,event,at=None) ->409 if restricted;
require_publishable_event(db,event); require_mutable_event(db,event) (terminal only);
can_read_event(db,event,viewer_id=None,at=None) bool; require_readable_event(...)->404.
Policy reads never lock/mutate. Sweep only before event locks.

Boundary worker exclusive: planning/service.py, media/service.py, social/service.py,
featured/service.py and tests/shared/test_sprint22_visibility.py. Integrate shared
policy (not duplicate predicates). Hide/suspension preserves participant access;
terminal denies public content, banner access only existing private staff path.
Saved hidden projections null even if participant (private bookmark remains).
No changes to shared policy/Events/Registrations/Attendance/router/migrations.

UI worker NEW features/eventsafety/** + tests/sprint22-eventsafety-ui.test.mjs.
Exports EventReportButton({eventId,token}), EventSafetyControls({eventId,token}),
OrganizationSuspensionPanel({orgId,token}), EventSafetyQueue({token,orgId?}),
safetyMessages. Reporter button may be attendee mobile; management desktop-only,
lazy/scoped requests, captured versions/keys and safe retries, native accessible
confirmation Cancel/Escape/focus return, English/Filipino, no browser persistence.
Coordinator mounts reporter in EventDetail; controls per staff event; org panels/
queue in staffworkspace and platform queue/admin selected org. No redesign.

QA worker NEW tests/quality/test_sprint22_quality.py and validation report only.
Real PostgreSQL tests serial by coordinator, no worker DB suites/builds/Git.
Preserve all37 existing tables (76 fictional rows,2 real rows). Never startup
migrate or touch Penpot/cloud app SQL. Publish verified checkpoint to GitHub per
standing instruction, no forcepush/deploy. Browser/Next security release gates
remain explicit; no Sprint23 automatic expansion.

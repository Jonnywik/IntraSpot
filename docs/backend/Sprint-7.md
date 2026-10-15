# Sprint 7 — local communication and safety

Authorized 2026-10-14. Preserve Sprint 6 and existing development data. Local,
fictional MVP only. No cloud, real OAuth, uploads, DMs, announcements, membership
lifecycle, event-content reporting, or Penpot changes. Main coordinates Luna/max
workers; shared PostgreSQL tests MUST run serially, with a coordinator-granted slot.

## User decisions and conservative implementation boundaries

- Guests read published-event comments. Only eligible signed-in PLM stakeholders
  comment/react/report. Comments and reactions stop changing at event start;
  comments remain readable afterward. No comment replies or edits in this slice.
- Six reactions: `interested` (Interested, star), `excited` (Excited, celebration),
  `support` (Support, gold heart), `kudos` (Kudos, applause), `wow` (Wow, surprise),
  `relate` (Relate, welcoming hug). One active reaction per user/event. Selecting
  another replaces it; selecting the current one removes it. Never changes seats.
  Use an explicit desired reaction-or-null API, not a retry-sensitive server toggle.
- Content reports start with organization owner/admin/moderator review; escalation
  and explicit reports against a person go to platform review. Existing server-side
  `platform_admin` supplies the local platform-moderator capability; no editable role.
- Reported content stays visible until staff action. Reporter can hide it for their
  own account only, and restore it. Staff may dismiss, remove or escalate content;
  personal reports allow dismiss or warn. Removal is global, not automatic on report.
- One active report per reporter/target, including concurrency/retries. Different
  people may report the same item. No self-reporting. Reporting a message/comment
  does not impose a personal-account restriction; reporting the person explicitly
  does, under the canonical pending-person-report rule.
- Pending personal review blocks event creation/publication and sending comments/
  chat, but not registration, reading, reaction, withdrawing or existing seats.
  Dismiss/warn/expiry ends that restriction; no automatic permanent ban.
- Plain text only. Render as text, never HTML. Public author label is `PLM member`
  unless global persona visibility permits a nickname; self may see `You`. Chat
  may additionally use per-event consent before event end. Never expose emails,
  profile fields, images, full rosters or tokens through communication surfaces.
- Confirmed registration is required for event chat, including staff. Pending,
  waitlisted, cancelled and reconfirming attendees cannot access chat. Staff access
  to report evidence is separate and does not grant chat access.
- At scheduled event end, chat becomes read-only and stays in the same inbox with
  Archived and deletion countdown. Access ends exactly 72 hours after end, even if
  cleanup is delayed. No separate archive tab. Scheduled-end metadata is authoritative.
- Organization report deadline: seven days. Expiry escalates to platform for up to
  fourteen additional days, measured from the stored deadline (not catch-up time).
  Manual escalation instead starts its fourteen-day platform window at the action
  timestamp, so an early escalation never extends platform review beyond two weeks.
  Platform expiry closes the report. Chat evidence is available only to authorized
  staff while an unresolved case is within its review deadline. Clear evidence on
  resolution/expiry. At chat expiry, physically delete original messages; report
  copies may remain under that bounded hold, inaccessible to attendees.
- Implement through existing APIs/polling, not WebSockets. Generic durable in-app
  notices contain no chat/comment body, reason text, email or persona. No external
  email or push. Poll only while the relevant view is active; abort on account change.

## Frozen domain models (SQLAlchemy and migration parity)

All IDs use String(36), UUID validation at API boundaries; timestamps UTC; foreign
keys reference existing users/events. Defaults follow app.db.models.now/uid.

Social owns:

- `EventReaction` table `event_reactions`: id PK, event_id FK, user_id FK, kind
  String(16) checked to the six keys, created_at UTC, updated_at UTC; unique
  `(event_id,user_id)` named `uq_event_reactions_user_event`.
- `EventComment` table `event_comments`: id PK, event_id FK, author_id FK,
  sequence BigInteger Identity unique, body Text nullable, body_hash String(64)
  nonnull, client_key String(128) nonnull, created_at UTC, removed_at UTC nullable;
  unique `(event_id,author_id,client_key)` `uq_event_comments_client_key`, index
  `(event_id,sequence)` `ix_event_comments_event_sequence`.

Chat owns:

- `ChatMessage` table `chat_messages`: same fields/constraints as EventComment,
  names `uq_chat_messages_client_key`, `ix_chat_messages_event_sequence`.
  No separate room/roster/read-state table is needed: published event + confirmed
  registrations + scheduled end determine the room and its lifetime.

Moderation owns:

- `ContentReport` table `content_reports`: id PK; event_id/org_id/reporter_id/
  subject_user_id FKs; kind String(16) checked comment/message/person; target_id
  String(36) opaque original content/user ID (no content FK so originals can purge);
  reason String(24) checked harassment/spam/deception/impersonation/other;
  status String(24) checked open/escalated/dismissed/removed/warned/expired;
  stage String(16) checked organization/platform; evidence Text nullable;
  created_at UTC, deadline UTC nonnull, resolved_at UTC nullable. Partial unique
  `(reporter_id,kind,target_id)` while status open/escalated named
  `uq_content_reports_active_reporter_target`; indexes event/stage/deadline and
  subject/kind/status/deadline. Evidence is a content snapshot, never a profile.
- `ReportDecision` table `report_decisions`: id PK, report_id FK, reviewer_id FK
  nullable for automatic timeout transitions, action String(24) checked
  dismiss/remove/escalate/warn/expire, created_at UTC. Preserve audit metadata;
  never store body/reason in notifications or logs.
- `ContentHide` table `content_hides`: id PK, user_id/event_id FKs, kind String(16)
  checked comment/message, target_id String(36), created_at UTC; unique
  `(user_id,kind,target_id)` `uq_content_hides_user_target`.

Coordinator adds notifications.read_at UTC nullable and migration `mvp_0005`.
Do not modify migration files, shared models or imports in workers. Migrations
preserve all old rows; downgrade refuses if new domain rows/read states exist.

## Frozen API shapes and responsibilities

All routes under `/api/v1`, strict extra-forbid input, existing error envelopes.
Content create body `{body:string, client_key:UUID}`: trim/validate 1..2000 chars.
Same event/author/key retry with same body hash returns existing item; conflicting
body returns 409. UUID/header verification stays in existing identity boundary.

`ContentItem`: id, event_id, author_id, author_label, sequence:int, body:string|null,
created_at, removed:bool, locally_hidden:bool, mine:bool. Tombstones/hides have no
body. Never serialize raw ORM user/profile, client_key or body_hash.
`ContentPage`: items:list[ContentItem], next_before:int|null. Stable sequence paging,
bounded limit default50/max100. Comments newest first, messages chronological.

Social routes:

- GET `/events/{id}/reactions` -> `ReactionSummary {counts:dict[sixkeys,int],
  total:int, mine:reaction|null, can_react:bool}`; guest-readable published only.
- POST `/events/{id}/reactions` `{reaction:sixkey|null}` -> ReactionSummary. Sets
  desired state atomically under event lock; retries do not toggle back. Synchronize
  existing event.interest_count by Interested delta, preserving pre-existing totals.
- GET `/events/{id}/comments?before_sequence&limit` -> ContentPage; public, draft404.
- POST same path -> ContentItem; only eligible actor, pre-start, no pending-person
  restriction, idempotent by client_key; never require registration to comment.
- DELETE `/events/{id}/comments/{comment_id}` -> ContentItem; author only; tombstone,
  never discard an existing report's retained evidence.
- Seam `remove_comment_locked(db,comment_id,event_id,at)` marks removed/body null.

Chat routes:

- GET `/me/chats` -> list[ChatInboxItem]: event_id,event_title,organization_name,
  ends_at,deletes_at,status:active|archived,latest_at:UTC|null. Confirmed-only before
  deletes_at; no full roster. Metadata contains no latest-message body.
- GET `/events/{id}/chat?after_sequence&before_sequence&limit` ->
  `ChatThread {event_id,event_title,status,deletes_at,can_send:bool,
  items:list[ContentItem],next_before:int|null}`; confirmed-only, chronological;
  Coordinator refinement: `removed_ids:list[UUID]` returns retained tombstone IDs
  to clear already-cached message bodies during polling. It exposes no content or
  roster and is never truncated silently; payload may grow within the 72h window.
  default latest page, after_sequence fetches newer messages. Reject both cursors.
- POST `/events/{id}/chat/messages` -> ContentItem, confirmed/pre-end/unrestricted;
  event lock serializes with withdrawal/reconfirmation. Idempotent client_key.
  Send generic `chat_message` notice to other current confirmed attendees, once.
- Seam `remove_message_locked(db,message_id,event_id,at)` tombstones body.
- Seam `purge_event_chat_locked(db,event,at)` removes original messages and their
  personal hide entries after deletes_at; bounded report copies remain separately.

Moderation routes:

- POST `/events/{id}/reports` `{kind:comment|message|person,target_id:UUID,
  reason:enum}` -> `ReportReceipt {id,event_id,kind,target_id,status,stage,deadline}`.
  Message reports require current confirmed-chat access, including archived access.
  Comment reports require published visible item. Person reports identify the
  author through a visible comment/message in that event; never arbitrary private
  account lookup. Return existing active report for duplicate reporter/target.
- GET `/me/reports` -> list[ReportReceipt], caller-only; no evidence/other reporters.
- POST `/me/content-hides` `{event_id:UUID,kind:comment|message,target_id:UUID,
  hidden:bool}` -> `{hidden:bool}`. Authorize underlying item access, own-account only.
- GET `/moderation/reports?org_id` -> list[ReportReview], stage-authorized staff only.
- GET `/moderation/reports/{id}` -> ReportReview; evidence only when authorized,
  unresolved and before deadline. Closed audits remain readable to appropriate staff.
- POST `/moderation/reports/{id}/decision` `{action:dismiss|remove|escalate|warn}` ->
  ReportReview. Content supports dismiss/remove/escalate; person dismiss/warn only
  at platform. Actor/time derived on server. Same terminal decision safe, conflicting
  decision409. Global removal calls target-domain seam under same event lock.
- `ReportReview` extends ReportReceipt: org_id,reason,reporter_id,subject_user_id,
  evidence:string|null,decisions:list[{id,reviewer_id,action,created_at}].
- Seams `has_pending_person_report(db,user_id,at=None)` and
  `catch_up_reports_locked(db,event,at)`; process durable deadlines, clear expired/
  resolved evidence, do not silently remove live content on expiry. Notify reviewers/
  reporter/subject generically with decision/transition scoped dedupe keys.

Coordinator supplies `app.core.communication.require_communication_allowed(db,
user_id,at=None,lock=False)` (raises403 under pending personal review),
`author_label(user,viewer_id=None,persona_shared=False,before_end=False)`,
`is_locally_hidden(db,user_id,kind,target_id)`. Lazy cross-domain imports keep model
initialization safe. All content/report mutation lock order: event, then affected
User row if needed, then report/content rows; never lock a user then an event.
  User metadata locks use PostgreSQL NO KEY UPDATE (SQLAlchemy key_share=True),
  preserving metadata serialization while allowing notification foreign-key reads.
For create/publish, retain organization/event lock order before communication check.
Catch-up and deletion run explicitly through the existing local deadline runner.
Public reads never mutate state or perform physical cleanup.

## Write ownership

1 Social backend: app/domains/social/**, tests/social/** ONLY.
2 Chat backend: app/domains/chat/**, tests/chat/** ONLY.
3 Moderation backend: app/domains/moderation/**, tests/moderation/** ONLY.
4 Attendee frontend: features/communication/**; app/chat/page.tsx; EventDetail.tsx;
  MyEvents.tsx confirmed chat entry ONLY. Use component-local CSS, no shared CSS.
5 Management frontend: features/moderation/**, organization workspace/admin screens
  ONLY. No mobile management. Consume frozen API contracts, no static outcomes.
6 Independent QA: tests/shared/test_sprint7_quality.py, docs/validation/sprint7-
  quality-review.md ONLY. Main schedules PG execution, QA does not reset shared DB.

Main exclusively owns infrastructure, router/model registration, migrations,
Actor/current-user restricted flag, event creation/publication checks, notification
read states/polling, generated API types, shared types/hooks, feed preview integration,
deadline runner, cross-domain/browser gates and acceptance documentation. Request
shared changes; do not edit another owner's files. No dependency upgrades.

## Exit gates

Guest reads but cannot post; six reactions swap/remove without registering or
overcounting; concurrent/retried messages/comments do not duplicate; no private
profiles/emails or draft content leak. Confirmed-only chat access is revoked on
withdrawal/reconfirmation, archived read-only at end and inaccessible at 72h.
Personal hides do not affect anyone else. Report routing, staff-role isolation,
one active report, explicit pending-person restrictions, audit/notification dedupe,
retention hold/expiry and independent-process restart catch-up pass PostgreSQL.
Desktop/mobile browser journeys, viewport fit, old Sprint 5/6 journeys, migration
preservation, OpenAPI/types, lint/build and credential scans pass. Stop at local
acceptance; participant testing/security review still gate real-user release.

## Local acceptance checkpoint — 2026-10-15

The integrated backend suite passed 257 tests (three browser opt-ins skipped in
that run); all three browser gates subsequently passed separately. This includes
the nine Sprint 7 communication/safety groups, eight approval/reconfirmation
groups, and ten core journey/viewport/restart groups. Nine frontend contract tests,
lint, TypeScript/static export, credential guards and Alembic drift checks passed.
The final core rerun repaired social-preview card fit through related spacing,
without shrinking text/artwork or weakening the viewport assertion.

See [Sprint 7 acceptance and remaining limits](../validation/sprint-7-acceptance-2026-10-15.md)
for evidence, the explicit retained-tombstone payload limit, runtime reproduction,
and the still-open participant/security/cloud release gates. Canonical vault notes
were not written outside the workspace. No real-user release is authorized.

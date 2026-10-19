# Sprint 14 — organization announcements and reactions

Authorized 2026-10-19: proceed to the next accepted roadmap sprint. Preserve
Sprint 13 and all uncommitted work. Local fictional MVP only. No real sign-in,
cloud, deployment, Penpot, uploads, forum/comments, new persistent navigation,
notification broadcasts, commit/push or Sprint 15. Participant/native-device
validation and long-term revision/deleted-content retention remain release gates.

## Frozen domain and security contracts

Use a new `announcements` domain, existing organization authorization, shared
six reaction kinds/ReactionInput/ReactionSummary, communication restrictions,
notification helper, error envelope and UI conventions. Reports are not tied to
events: use dedicated announcement report/audit rows rather than inventing an
event or weakening existing event-report foreign keys/DTOs.

Only eligible active owner/admin of an approved organization may publish/edit/
remove. No announcement drafts in this sprint. Moderators/members only read and
react; platform privileges alone do not confer authoring membership. Public
posts are guest-readable. Members-only posts require current PLM eligibility and
active membership of THAT organization, including staff. Recheck DB membership
on every read/write; never trust browser flags or stale actor grants. Unauthorized
direct IDs return 404 without body/title/revisions/reaction counts. Public reads
only expose approved organizations' posts. Hidden/removed posts are unavailable
to ordinary readers. No roster, email, persona or individual reactor list.

All announcement mutations lock organization, then announcement, then report/
reaction/revision rows. The existing membership lifecycle locks organization,
so revocation and access decisions serialize without a new authorization cache.
This deliberately coarse lock fits the local pilot; no new locking framework.

### Models (coordinator owns migration; domain agents own their new model files)

`announcements.models.Announcement`: table `announcements`:
id String36 PK; org_id FK organizations; created_by FK users; title String200;
body nullable Text (null only after removal); audience String16 public|members;
version Integer default/server 1, positive; client_key String36;
create_hash String64; created_at/updated_at UTC required; edited_at/hidden_at/
removed_at UTC nullable. Unique(org_id,created_by,client_key), named
`uq_announcements_create_key`; index org_id,created_at,id. DB checks named
`ck_announcements_audience`, `ck_announcements_version`,
`ck_announcements_body` (body required unless removed).

`AnnouncementRevision`: `announcement_revisions`: id PK; announcement_id FK;
version positive Integer; actor_id FK users; action String16
publish|edit|remove|hide|restore; title String200; body nullable Text;
audience public|members; created_at UTC. Unique(announcement_id,version),
`uq_announcement_revisions_version`; checks audience/action/version with prefix
`ck_announcement_revisions_`. Manager-only history, never public snapshots.

`AnnouncementReaction`: `announcement_reactions`: id PK; announcement_id FK;
user_id FK users; kind existing six values; created_at/updated_at UTC.
Unique(announcement_id,user_id) `uq_announcement_reactions_user_post`;
check `ck_announcement_reactions_kind`.

`announcements.moderation_models.AnnouncementReport`: `announcement_reports`:
id PK; announcement_id FK; org_id FK; reporter_id/subject_user_id FK users;
reason existing five report reasons String24; status String24
open|dismissed|hidden|restored|removed|expired; reported_version positive Integer;
evidence nullable Text; created_at/deadline required UTC; resolved_at nullable UTC.
Checks `ck_announcement_reports_reason/status/version`. Partial unique index
`uq_announcement_reports_active_target` on reporter_id,announcement_id WHERE
status='open'; index `ix_announcement_reports_org_deadline` org_id,status,deadline.

`AnnouncementReportDecision`: `announcement_report_decisions`: id PK; report_id
FK; reviewer_id nullable FK users (null only automatic expiry); action String16
dismiss|hide|restore|remove|expire; created_at UTC; check
`ck_announcement_report_decisions_action`.

Use uid()/now() Python defaults and existing UTC type; do not add dependencies.

### Authoring and projections

Input: title trimmed nonblank 1–200, body trimmed nonblank 1–5000, audience enum;
create additionally requires UUID client_key. Same create key/hash reuses its row;
different payload conflicts. Preserve the original create hash on later edits.
PATCH/DELETE require quoted integer `If-Match`, conflict 409 on stale/missing
version. No-op same-content edits do not manufacture an Edited marker. Removal
is a soft tombstone, never physically deletes reports/revisions; repeated removal
is an authorized no-op. Each real change increments version and records a full
revision with actual server actor/time. Create starts version 1. `record_revision
(db, post, actor_id, action, timestamp)` records CURRENT version/state; caller
increments version first on mutations. Moderation uses this same helper.

Owners cannot edit platform-hidden posts or restore them by editing. They may
remove their own hidden posts. Removed posts cannot be restored. Local history
persists for review; this is NOT a settled indefinite production retention policy.

`AnnouncementOut`: id,org_id,organization_name,title,body(str|null),audience,
version,created_at,updated_at,edited_at, state visible|hidden|removed. No author ID.
Public list/detail never return hidden/removed; manager collection may include
tombstones. `AnnouncementRevisionOut`: id,version,actor_id,action,title,body,
audience,created_at. Stable lists newest created_at then id, limit 1–100 default50,
offset>=0; filter visibility BEFORE pagination. Auth-dependent reads private,
no-store and Vary Authorization.

API prefix /api/v1:
- GET/POST /organizations/{org_id}/announcements (public/current-member list;
  POST approved manager only; create response AnnouncementOut, status201).
- GET /organizations/{org_id}/announcements/manage (manager-only collection).
- GET/PATCH/DELETE /announcements/{announcement_id} (DELETE status204).
- GET /announcements/{announcement_id}/history (manager only).
- GET/POST /announcements/{announcement_id}/reactions using existing social DTOs.

Helpers for reports: `get_readable_announcement(db, announcement_id, actor,
lock=False)` returns visible/access-authorized Announcement or 404. Lock=True
must lock org then post. Reactions atomically add/replace/remove one row per
eligible viewer, repeat desired state idempotently, no attendance side effects.
Reaction privacy/access is identical to reading its post. No event-start cutoff
exists for announcements; hidden/removed/access-revoked writes fail.

### Reporting and moderation

Reporting requires eligible signed-in actor (reuse existing trust boundary; no
anonymous reporting added). Report only readable content, not own content; report
alone never hides it. Snapshot exact reported title/body and reported_version.
Repeated active report returns same receipt, no duplicate notifications. Current
author edits/removal must not rewrite or erase another OPEN report's evidence.
Report receipts are only the caller's, no evidence; own receipt recovery may
survive loss of content access without exposing the content.

All announcement reports go directly to verified platform admin review, never
organization report queue and never trigger personal-account restrictions.
Reuse existing PLATFORM_REVIEW_DAYS=14 and reasons. Evidence visible only to
platform reviewers while open and strictly before deadline. Purge on resolution
or expiry; delayed worker catch-up cannot extend read access. Never reconstruct
expired evidence from revision history. No user profile/email disclosure.

New API:
- POST /announcements/{id}/reports {reason}; status201, AnnouncementReportReceipt.
- GET /me/announcement-reports -> caller receipt list.
- GET /moderation/announcement-reports -> platform-only review list.
- GET /moderation/announcement-reports/{report_id} -> platform detail.
- POST /moderation/announcement-reports/{report_id}/decision {action}.

Receipt: id,announcement_id,org_id,status,deadline. Review adds reason,
reporter_id,subject_user_id,reported_version,evidence,decisions,
post_state(visible|hidden|removed),post_version. Audit fields same as existing
DecisionAudit but new action enum. Content actions hide/restore/remove require
If-Match current post version. Dismiss resolves an open case without changing
content. Hide resolves the case as hidden and hides the post globally. Restore
is permitted ONLY from that hidden case while the post is still hidden and not
removed; it can occur after the evidence deadline because hidden text cannot be
edited. Restore clears hiding and records restored audit/status; it does not
recreate evidence. Remove resolves open/hidden case as removed and tombstones
the post permanently. Same final-action retries do not duplicate mutations/audits.
Different terminal actions conflict except the explicit hidden→restore/remove
transition. Expired open cases cannot decide. Other active cases' snapshots
remain intact, and reporting never automatically hides or suspends anyone.

`catch_up_announcement_reports_locked(db,org_id,at)` assumes org lock, expires
open due cases with one audit/notification transition and evidence purge. Add it
to the existing explicit deadline runner's org loop; no startup timer/migration.
Safety notifications may use the existing helper with org_id and no event;
dedupe per report/transition/recipient. No broadcast announcements notifications.

## UI and ownership

Keep approved Quiet Heritage, language/contrast/text/motion settings and four
mobile destinations. Announcements live within existing organization profile;
public/eligible member access is explicit, no new Community nav. Owner/admin
desktop workspace gets author/edit/remove/history controls with honest loading,
empty/error/retry/conflict states and a visible Edited marker. All visitors see
six aggregate reactions; only eligible authorized readers can change theirs.
Read-only means no comments/forum. Mobile can read/react/report but never manage.
Platform desktop review gets announcement-specific queue/actions beside existing
reports; do not alter their event/person action semantics or DTOs.

Four Luna/max workers, disjoint write sets:
1. Announcement core: new models/schemas/service/routes and tests/announcements/
   core/reaction tests. No shared models/migrations/router/types.
2. Announcement safety: new moderation_models/report_schemas/report_service/
   report_routes; report tests; new frontend AnnouncementReportQueue + own CSS
   and announcement-report-messages dictionary. Existing report files untouched.
3. Organization UI: new features/announcements/*, MemberPortal.tsx and workspace-
   page.tsx integration, announcement-messages dictionary, frontend tests. Do not
   edit moderation UI, generated/shared types, i18n or admin page.
4. Independent QA: new shared cross-domain tests, opt-in browser wrapper and
   docs/validation/sprint14-browser-check.mjs. No app or migration changes.

Coordinator owns shared imports/routers, Alembic mvp_0010, model registration,
deadline integration, generated OpenAPI/types, dictionary assembly/admin queue
mount, isolated test serialization, local fixtures/runtime and handoff.

## Acceptance and stop

Prove guest/public and current-member visibility before pagination; direct ID,
reaction, history and cross-org isolation; revoked membership/ineligible actor
denial; approved owner/admin authoring; moderator denial; stale write protection;
create/reaction retries and concurrency; owner edit/removal under open reports;
all moderation actions, bounded evidence/restart expiry, audit actors and no
personal restriction; migration preservation/guarded rollback. Live Edge desktop/
mobile, Filipino XL, four tabs, end-to-end owner/member/guest/admin actions and
affected prior regressions. Preserve dev DB, renew ignored fictional credentials
only via existing helper, restore ports3000/8001 and deadline worker. Report
actual results and deferred participant/retention decisions. Stop before Sprint15.

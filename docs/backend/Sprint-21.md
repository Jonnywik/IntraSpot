# Sprint 21 — manual staff attendance

Frozen implementation contract, 2026-10-24. Existing desktop event workspaces
only. Eligible active owner/admin/moderator of the same approved organization
may read attendance, open/close check-in and mark/correct confirmed attendees.
Default closed, including existing events. It stays open after event end until
staff close it; no automatic no-show decision. Marked/unmarked are not
registration states and must not change capacity, waitlists, chat or consent.
No QR, helper role, mobile management, emails or public/attendee roster.

API `/api/v1` (all protected staff-only):

- GET `/events/{event_id}/attendance`: `AttendanceOut` with event_id, is_open,
  version (default 0), writable (published/approved), confirmed_count,
  checked_in_count, attendees list. Each attendee: registration_id,
  participant_label (opaque `Registration · UUID`, no email/profile), attended bool.
  Only status exactly confirmed, stable admission_order/id order. Do not include
  pending/waitlisted/reconfirmation-required/cancelled/rejected registrants.
- GET `/events/{event_id}/attendance/history`: latest 100 `AttendanceAuditOut`
  rows: id, event_id, actor_id, action (`session`|`mark`), registration_id nullable,
  previous_value bool, value bool, version, created_at. No private profile data.
- POST `/events/{event_id}/attendance/session`:
  `{is_open: StrictBool, version: StrictInt >= 0, client_key: UUID}`.
- PUT `/events/{event_id}/attendance/registrations/{registration_id}`:
  `{attended: StrictBool, version: StrictInt >= 0, client_key: UUID}`.
  Both writes return `AttendanceMutationOut`: event_id, registration_id nullable,
  is_open, attended nullable, version, recorded_at. All extra input forbidden.

Every accepted new command increments the single event attendance version once
and produces one immutable audit with stored original response/payload hash.
Same actor/key and same path/body/version retries return the stored response
without duplicating effects. Incompatible reuse conflicts. Recheck current staff
authority even for retry; no former-staff history recovery. Client retains exact
in-memory request on uncertainty; never silently adopts a refreshed version.
After any response refresh roster/state/history before fresh actions.

Reuse advisory client-key lock, then organization lock, then event lock. All
registration/capacity writers already lock the event; lock attendance state and
target registration only after it. Recheck authority after waiting for locks.
Mark/correction requires check-in open and a current confirmed registration for
that exact event. Closing and marking races serialize; stale versions conflict.
Accept open/close after end; no start/end gate. Read requests do not mutate.
No automatic opening or migration backfill of marks. Keep records if a
registration later cancels; current confirmed roster/count excludes it.

Models (new domain attendance):
- AttendanceSession: event_id PK/FK events, is_open bool false, version int >=0.
- AttendanceMark: registration_id PK/FK registrations, attended bool false.
- AttendanceAudit: id String36 PK, event_id FK, actor_id FK users, client_key
  String36, payload_hash String64, action String16 check session/mark,
  registration_id nullable FK, previous_value bool, value bool, version int>0,
  result JSONB nonnull, created_at UTC. Unique(actor_id,client_key), index on
  (event_id,created_at). Audit also stores original retry outcome.

Coordinator owns reviewed additive mvp_0016 after mvp_0015, router assembly,
model imports, OpenAPI/types, existing workspace integration/i18n/package scripts,
database execution and preservation. Workers own only assigned domain/panel/tests.
Downgrade refuses non-empty attendance data, no startup migrations. Preserve all
34 prior tables in both isolated development databases.

Lifecycle boundary: event cancellation/removal does not yet exist in this code's
event schema or API. Do not invent those workflows in this sprint. Non-published
or unapproved events and non-confirmed registrations fail closed for writes.
Full event cancellation/removal integration is an explicit Sprint 22 dependency,
not a claimed passing check in Sprint 21. Record this limitation in acceptance.

UI export `AttendancePanel({eventId, token})` in features/attendance. Lazy expandable
desktop panel; fetch only while expanded and desktop. Same visual tokens,
English/Filipino copy, status+text, accessible confirmation for session changes,
Cancel focus/Escape/focus return, roster search locally by opaque label, no email
lookup. The attendee's own My Events/result shows the matching registration
reference, not another person's data; it is an identifier, not identity proof.
Show open/closed and counts, Check in/Clear check-in per confirmed row,
read-only history, loading/empty/forbidden/retry/conflict/success. Clear is an
explicit correction, not registration withdrawal. Account/event cleanup aborts
requests and clears private state. No browser storage of roster/commands.

Proof: isolated PostgreSQL role/cross-org/privacy, exact confirmed-only scope,
after-end operation, closed gate, stale version/idempotency, immutable audit,
concurrent toggles/marks and role revocation; unchanged participation. Frontend
helpers/contracts/localization/type/lint/build checks. Live browser and existing
Next.js 16.4.0 security gates stay honestly open if unavailable. Commit/push each
sprint checkpoint after checks (user standing instruction, 2026-10-24); no
deployment, force push or silent release approval.

# Sprint 21 — manual staff attendance

Date: 2026-10-24. **Implemented locally; final acceptance remains open.**
This checkpoint is developer evidence, not participant or deployment approval.

## Delivered

- Existing desktop owner/admin and moderator workspaces provide an expandable
  attendance panel for their organization's events. No new mobile-management
  destination, QR check-in or helper role.
- Check-in defaults closed. Authorized eligible active owners/admins/moderators
  open/close it and mark or clear check-ins for currently confirmed registrations.
  It remains open after event end until staff close it; unchecked is not a no-show
  decision. Attendance does not change registrations, seats, waitlists, chat or
  consent.
- Staff see registration references, not emails, user IDs, nicknames or profile
  text. Confirmed attendees see the same own reference in My Events and the
  registration result. The reference is an identifier, not proof of identity.
- Current-role authorization, version checks, stable request keys and PostgreSQL
  locking protect writes. Same-key identical retries return the original stored
  outcome without extra audit/effects; incompatible reuse conflicts. A former
  owner cannot replay a privileged attendance command after ownership transfer.
- Read-only scoped history includes actor, time and old/new values. Marks/audits
  remain after registration cancellation, but cancelled registrations leave the
  current confirmed roster/count and cannot receive new marks.
- English/Filipino feedback, confirmation, loading/error/retry/conflict states,
  in-memory uncertain retries and account/event request cleanup are integrated.
  No private roster or request is persisted in browser storage. After mutations,
  state/roster/history refresh before new commands; refreshes queue behind an
  existing read.

## Database safety

Reviewed additive `mvp_0016` follows `mvp_0015` and was explicitly applied to both
isolated development databases. No startup migrations or data backfill.
`attendance_sessions`, `attendance_marks` and `attendance_audits` are new tables.
The audit stores immutable command payload identity and original retry outcome;
actor/client-key uniqueness is enforced in PostgreSQL. Downgrade refuses to
silently discard any attendance data, including session rows.

Aggregate hashes matched all **34 pre-existing tables**: **76 fictional-development
rows** and **2 real-development rows**, including prior Featured/persona/ownership
state. No development attendance records were seeded. Scratch tests are isolated
from both development databases; Penpot and cloud application data were untouched.

During final verification Docker had restarted and the IntraSpot database
container was stopped. Read-only diagnosis confirmed its existing named volume
and loopback port. The same container was started without resetting data or
restarting Penpot. Interrupted checks were stopped and rerun; both preservation
checks passed afterward.

## Actual verification

Three non-overlapping GPT-6 Luna/max workers handled the attendance backend,
desktop panel and independent HTTP QA. The coordinator owned shared integration,
migration, OpenAPI/types, serial database execution and delivery.

| Gate | Result |
|---|---|
| Foundation/migration + existing organization/membership regression | 45 passed |
| Existing registration/capacity/waitlist/chat/persona/ownership regression | 93 passed |
| Attendance domain (including three races), migration and prior-history checks | 23 passed |
| Independent HTTP QA after corrected reference expectation and DB recovery | 3 passed |
| Distinct passing default PostgreSQL cases across those runs | **161**; overlapping infrastructure cases counted once, not a full repository rerun |
| Separate synthetic Supabase/auth protocol suite | **50 passed**; not live PLM-account sign-in |
| Complete final frontend Node suite | **130 passed** |
| Whole-frontend ESLint and TypeScript | Passed |
| Default and real-auth builds | Both compile, type-check and generate 14 routes, then stop with the existing Next.js 16.4.0 security advisory; final build gates remain open |
| Alembic drift and Python syntax checks | Passed |
| Existing development data preservation | Passed, both profiles |

Concurrency tests cover duplicate same-key writes, close-versus-mark version
serialization and current-role revocation before retry. Independent HTTP journeys
cover same-org staff/guest/member/foreign/platform-admin boundaries, historical
events, confirmed-only roster, cross-event registration mismatch, ownership
transfer and registration withdrawal without attendance side effects.

Review caught a retry response being compared with a later refreshed session
state: retries now validate the originally captured state, so a committed mark
remains recoverable after another staff member closes check-in. Audit display
also includes opaque actor references and before/after values. Early test-only
mismatches were corrected without weakening policy: an unapproved organization
returns existing 403 before the unpublished-event 409 gate, and the opaque
reference contract was clarified from Member code to the attendee's matching
registration UUID. Final localization includes the retry and refresh messages.

Ignored evidence: Backend `.cache/s21-foundation.xml`, `s21-regression.xml`,
`s21-attendance.xml`, `s21-quality.xml`, `s21-auth.xml`, `s21-evidence.ps1` and the
two preservation baselines. See [contract](../backend/Sprint-21.md),
[interaction handoff](../design/sprint21-interaction-handoff.md) and
[independent review](sprint21-quality-review.md).

## Open acceptance gates and non-goals

1. **Event-level cancellation/removal integration:** the current event schema/API
   has no such lifecycle state or workflow. This sprint fails closed for
   unpublished/unapproved events and non-confirmed registrations; it does not
   invent event cancellation/removal or claim that integration passed. Resolve
   and wire the lifecycle write guard in Sprint 22, including direct links and
   retained attendance history.
2. **Live browser:** no new screenshots or live desktop/mobile/keyboard proof.
   Earlier browser access was policy denied on an internal-error page; no
   alternate/hidden-browser workaround was used. Open the real local app before
   reviewing expansion, open/close confirmation, marking/correction, matching own
   references, error/conflict/retry feedback, focus return, account changes and
   mobile absence. Source/helper checks are not interaction testing.
3. **Dependency security/build:** Next.js 16.4.0 is unchanged. Both final build
   commands stop on the advisory after route generation. Recommend resolving the
   security update before release; no security suppression, automatic dependency
   upgrade or release approval was performed.
4. Participant/native-device/full language/dark/contrast/larger-text checks,
   live PLM-account sign-in and operational security/release review stay separate.

Standing instruction recorded in `AGENTS.md`: commit/push each sprint checkpoint
after implementation and verification, keeping unresolved gates explicit and
excluding local secrets/data/build output. A push is not deployment. Sprint 22
has not been started in this checkpoint.

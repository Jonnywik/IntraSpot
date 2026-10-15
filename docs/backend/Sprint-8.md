# Sprint 8 — local organization membership lifecycle

Status: local implementation and verification completed on 2026-10-15. All user
choices are confirmed (`9A 10A`); the frozen contracts below record the workers'
non-overlapping responsibilities. See the
[Sprint 8 acceptance and handoff](../validation/sprint-8-acceptance-2026-10-15.md).
The accepted Sprint 7 MVP and real-user release gates are preserved.

## User decisions — 2026-10-15

The user selected `1C 2A 3B 4B 5A 6B 7A 8C` and requested execution.

1. An authenticated person may apply and receive approval before PLM eligibility;
   organization member features and workspace access stay locked until trusted
   PLM eligibility is established. This is not authorization to bypass existing
   eligibility checks for registration, social features or organization publishing.
   Guests without an account cannot acquire an anonymous membership.
2. Requests contain no written application note. Persona sharing is separately
   optional and default-off.
3. A rejected membership applicant may reapply immediately. This is distinct from
   organization accreditation rejection, whose existing read-only behavior stays.
4. Applicants may withdraw a pending request. Reapplication to that organization
   is blocked for 24 hours after withdrawal; rejection adds no cooldown.
5. Eligible active owners, admins and moderators may approve/reject requests.
6. Membership-review consent exposes nickname and interests only, while pending.
   It never exposes age bracket, pronouns, icebreaker, email or profile photos;
   event/global consent does not silently carry over. End this access on approval,
   rejection or withdrawal.
7. Rejection uses an applicant-visible predefined reason, not free text. Record
   the real deciding staff account and server time; send a generic in-app notice
   for approval/rejection without private profile data or reason text in notices.
8. Include applications/review, targeted invitations, leaving/removal and staff
   role changes. Automated ownership succession, announcements, recommendation
   ranking, flash events and cloud deployment remain separate.

## Confirmed lifecycle choices

The user answered the two follow-up choices: seven-day invitation expiry and
the recommended self-service leaving/hierarchical removal permissions.

9. Invitation expiry: seven days. Common safeguards: local in-app delivery only,
   intended-account-bound, single-use, revocable, no transferable forwarded-link
   access, standard-member grant on acceptance with eligibility-gated access.
10. Non-owners may leave; owner/admin may remove members or moderators, with
    admin removal owner-only. Owners cannot leave or be
    removed while they remain owner; ownership transfer/succession is not included.

The existing canonical consequence of ending membership remains: cancel affected
organization registrations/waitlists, release capacity safely, promote appropriate
waiters, revoke organization-event chat access and notify the affected person.
Preserve historical records and immutable retry receipts rather than deleting
attendance history. Departures end existing participation; they do not invent a
permanent ban on otherwise-public event registration or membership reapplication.

## Shared implementation and verification boundaries

- Keep local fictional identities, the separate PostgreSQL 17 MVP database and
  existing FastAPI modular domains. Never use Penpot's database or cloud services.
- Derive eligibility from trusted stored identity; no browser eligibility flag,
  arbitrary-user login, new public email collection or editable platform privilege.
- Preserve one effective role per person/organization. Owner retains admin-grant
  control; admins may manage moderator roles; moderators cannot manage staff roles.
  Approval/invitation never silently restores a former privileged staff role.
- Reuse existing capacity, waitlist, notification and chat authorization rules.
  A membership departure must not partially revoke access while leaving orphaned
  seats or issue duplicate promotions/notices on retry. Check races with new
  registrations, approvals, staff changes and competing departures in PostgreSQL.
- Migrations are reviewed, additive and explicit, preserve current data, and refuse
  destructive rollback over new lifecycle data. Never migrate on API startup.
- The main chat owns shared infrastructure, migrations, actor/router integration,
  generated API types, cross-domain lifecycle seams and final acceptance. Luna/max
  workers receive non-overlapping backend/frontend/test write scopes only after
  contracts and lifecycle policy are frozen. Database test runs remain serial.
- Keep organization management desktop-only. Attendee membership actions may use
  approved desktop/mobile shells without changing the four persistent mobile tabs.
- Verify privacy/eligibility, withdrawal cooldown, immediate post-rejection retry,
  role isolation, invitation replay/expiry/revocation, capacity-safe departure,
  chat revocation, real persisted browser journeys and all prior sprint regressions.
  Participant/security review still gates real-user release.

## Frozen models and API — coordinator contract

All IDs are String(36) with UUID validation at HTTP boundaries, timestamps UTC,
and client keys UUIDs stored as String(36). Domain package: `app.domains.memberships`.
No new dependency or authentication endpoint. Only approved organizations accept
new membership applications/invitations or membership-management changes; existing
pending drafting/accreditation behavior remains unchanged.

### Models (membership backend worker owns models.py)

- `MembershipApplication` / `membership_applications`: id PK; org_id FK organizations;
  user_id FK users; client_key; persona_shared bool default false; status String(24)
  pending/approved/rejected/withdrawn/superseded; created_at; resolved_at nullable;
  decided_by FK users nullable; reason String(32) nullable, limited to
  requirements_not_met/applications_closed/other. Unique(user_id,client_key);
  partial unique(org_id,user_id) WHERE status='pending'. Index(org_id,status,created_at).
- `MembershipInvitation` / `membership_invitations`: id PK; org_id FK; recipient_id
  FK users; sender_id FK users; client_key; status String(24)
  pending/accepted/declined/revoked/expired/superseded; created_at; expires_at;
  resolved_at nullable. Unique(sender_id,client_key); partial unique(org_id,recipient_id)
  WHERE status='pending'; index(status,expires_at). Check expires_at > created_at.
- `MembershipAudit` / `membership_audits`: id PK; org_id FK; actor_id FK users nullable
  (automatic expiry); user_id FK users; action String(40); old_role/new_role nullable
  String(16); created_at. Index(org_id,created_at). No persona, email or free-text body.
- `MembershipOperation` / `membership_operations`: id PK; org_id FK; actor_id FK;
  user_id FK; action String(24) leave/remove/role; client_key; payload_hash String(64);
  result JSONB nonnull; created_at. Unique(actor_id,client_key). Stored result is the
  immutable successful change receipt; incompatible same-key reuse is 409.
- `EventAccessRevocation` / `membership_event_revocations`: id PK; event_id FK events;
  user_id FK users; cutoff_order BigInteger >=0; created_at; updated_at.
  Unique(event_id,user_id). Records the last admitted registration order invalidated
  by a membership departure. Do not delete ended registration history.

Keep the existing OrgMembership model unchanged. Approved/invited membership uses
active=True as the grant record, but effective access ALWAYS also requires current
trusted PLM eligibility. Ineligible approvals expose only their own application/
invitation/status receipts, never active grants, My Clubs, roster, staff workspace
or chat. No browser route may change email/verification/eligibility. Membership
creation always grants member, never restores a former privileged role. Successful
grant audits use action `membership_granted`; joined_at is the latest such audit
timestamp, or null for legacy fixtures (do not fabricate old join dates).

### DTOs (membership backend worker owns schemas.py)

- `MembershipApplicationInput {client_key:UUID, persona_shared:bool=false}`.
- `MembershipDecisionInput {outcome:approved|rejected, reason:reason|null=null}`;
  reject requires a reason, approve forbids a reason. Reason labels are Membership
  requirements not met / Applications currently closed / Other membership criteria.
- `MembershipInvitationInput {recipient_id:UUID, client_key:UUID}`.
- `MembershipKeyInput {client_key:UUID}`; `MembershipRoleInput` additionally has
  role:admin|moderator|member (never owner).
- `MembershipApplicationOut`: id,org_id,organization_name,status,persona_shared,
  created_at,resolved_at,decided_by,reason,can_reapply_at:UTC|null,access_ready:bool.
  Same-key create retries return the same application identity/current status;
  differing frozen consent/org is 409. A new application needs a new key.
- `MembershipApplicationReview` extends that with user_id,applicant_label,
  persona:null|{nickname:string|null,tags:list[string]}. Persona exists ONLY while
  pending and separately opted in. Without that consent use generic applicant
  labels, even if a global/event persona flag is true. Closed reviews have no persona.
- `MembershipInviteOut`: id,org_id,organization_name,sender_id,recipient_id,status,
  created_at,expires_at,resolved_at,access_ready. Expiry is enforced at the exact
  boundary even if a worker has not persisted status='expired' yet.
- `MembershipSelfOut`: id,org_id,organization_name,role,active,access_ready,joined_at.
- `MembershipRosterItem`: id,user_id,label,role,eligible,access_ready,joined_at.
  Active grants only; use You / Member + short account code, not private nicknames.
  No browseable roster for ordinary members. No email/images/private persona.
- `MembershipChangeOut`: org_id,membership_id,user_id,role,active,
  cancelled_registrations:int,chat_revoked:int. Role changes have zero attendance counts.
- `MembershipAuditOut`: id,actor_id,user_id,action,old_role,new_role,created_at.

All inputs extra-forbid. Resolve actual actor/decision time server-side. Every
write route uses Depends(get_db, scope='function') and commits before success.

### Routes (all under /api/v1)

Applications/invitations worker owns `applications.py` + `routes_applications.py`:

- POST /organizations/{org_id}/membership-applications -> MembershipApplicationOut;
  any active authenticated account, no PLM prerequisite yet. Deny duplicate pending
  application or an already-active grant. Withdrawal cooldown is server-side/24h.
- GET /me/membership-applications -> list[MembershipApplicationOut], caller only.
- POST /membership-applications/{id}/withdraw -> MembershipApplicationOut, caller only.
- GET /organizations/{org_id}/membership-applications -> list[MembershipApplicationReview],
  owner/admin/moderator; include closed history, no expired consent.
- POST /organizations/{org_id}/membership-applications/{id}/decision -> review;
  owner/admin/moderator. Same terminal decision/reason safe; conflicting outcome409.
- POST/GET /organizations/{org_id}/membership-invitations -> invite / list[invite],
  owner/admin only. Invitee supplies their own existing account code (UUID); do not
  add a user directory, email lookup, public personal search or new identity system.
- POST /organizations/{org_id}/membership-invitations/{id}/revoke -> invite,
  owner/admin only; effective immediately.
- GET /me/membership-invitations -> list[invite], recipient only.
- POST /membership-invitations/{id}/accept or /decline -> invite, intended recipient
  only. Invitation UUID is not a bearer credential; forwarded links cannot accept.
  Repeated acceptance never reactivates membership after a later departure.
- On approval/acceptance, atomically grant member if not already active; close
  another pending application/invitation as superseded, without falsely recording
  an applicant as a staff reviewer or creating a withdrawal cooldown.
- `catch_up_invitations_locked(db,org_id,at)` persists overdue pending invitations
  as expired with an audit, safely repeatable. Own reads may project expiry read-only.

Lifecycle worker owns `access.py` + `routes_access.py`:

- GET /me/memberships -> list[MembershipSelfOut], caller status only, even if locked.
- GET /organizations/{org_id}/members -> list[MembershipRosterItem], staff only.
- GET /organizations/{org_id}/membership-audit -> list[MembershipAuditOut], staff,
  latest 100; no roster or audit for ordinary members/ineligible actors.
- PATCH /organizations/{org_id}/members/{membership_id}/role with MembershipRoleInput.
  Owner changes admin roles; owner/admin changes moderator/member roles. Changing
  a current admin also requires owner. Never change owner; no self-promotion.
  Only current eligible active members may be granted staff roles.
- POST /organizations/{org_id}/members/{membership_id}/remove with MembershipKeyInput:
  owner/admin remove member/moderator; owner-only removal of admin; never owner.
- POST /organizations/{org_id}/membership/leave with MembershipKeyInput: any signed-in
  non-owner may end their own grant, including an approved-but-locked grant.
- Departure sets active=False before attendance consequences, so departed staff
  cannot be selected as reviewers. Role changes alone do not cancel attendance.
  Repeated departure while already inactive must not cancel later public attendance.
- Obtain the operation key lock BEFORE organization lock. Authorize current staff
  under that organization lock, then return a stored compatible operation outcome
  without repeating effects. Own leave retries may recover after grant deactivation.

### Coordinator-provided shared seams

The membership backend worker implements `policy.py` with these exact functions:

- `lock_client_key(db,actor_id,key)` PostgreSQL transaction advisory lock keyed by
  actor/key, taken before organization lock to serialize same-key cross-org retries.
- `get_org(db,org_id,*,lock=False,approved=False)`; `get_user(db,user_id)` current
  active user; `eligible_user(db,user_id)` bool; `membership_for(db,org_id,user_id)`.
- `require_staff(db,user_id,org_id,*,roles=('owner','admin','moderator'),lock=False)`
  returns (Organization,OrgMembership), checks approved org/current eligible actor
  and current role. Do not acquire a user row lock before event locks.
- `access_ready(db,org_id,user_id)` bool; `joined_at(db,org_id,user_id)` timestamp|null.
- `audit(db,org_id,actor_id,user_id,action,at,*,old_role=None,new_role=None)`.
- `notice(db,org_id,user_id,kind,dedupe_key)` generic membership in-app notification.
- `grant_member_locked(db,org_id,user_id,actor_id,at)` -> OrgMembership; grant member,
  audit membership_granted, never restore staff. Applications worker handles other
  pending-path supersession in the same transaction.

Main supplies `app.domains.registrations.service.end_membership_attendance(db,
org_id,user_id)` -> tuple(cancelled_count,chat_revoked_count). Caller already holds
organization lock and has deactivated the grant. It locks ALL published org events
in stable ID order before touching attendance; captures each event.next_admission
as the durable revocation cutoff; cancels non-ended active participation, clears
review/reconfirmation state, releases/promotes safely and writes generic notices.
Ended registrations remain historical; revocation markers deny their retained chat.
Undrained receipts at/below cutoff cannot create seats later, including after restart.
New public registrations after departure remain allowed under existing eligibility
rules and get a later order; a successful new confirmation can restore that event's
chat. Original stored receipt outcomes are never rewritten.

Main extends Notification with nullable event_id and nullable org_id FK (at least
one context required), keeps old rows, and extends `notify_in_app` to accept org_id.
Main supplies approved public organization listing GET /organizations; updates
identity effective grants and all relevant access/notification reads; registers
routers/models, migrations, deadline catch-up, generated types, shared navigation
entry points, browser gates and acceptance.

### Frontend ownership and interfaces

- Attendee worker ONLY `features/memberships/MemberPortal.tsx`, `member-portal.module.css`.
  Export `MemberPortal` named component taking `{orgId?:string}`. It loads approved
  organizations, own requests/invites/memberships, shows shared account code from
  actor.id (no directory), request consent/note-free form, withdrawal cooldown,
  rejection reasons/immediate retry, invitation accept/decline and leave confirmation.
  Frozen mutation keys/payload on uncertain responses; no auto retry with new keys.
  Own pre-eligibility statuses remain usable; locked membership has explicit copy.
- Staff UI worker ONLY `features/memberships/StaffMembership.tsx`, `staff-membership.module.css`.
  Export `StaffMembership` taking `{orgId:string,role:string,onChanged?:()=>void}`.
  Desktop-only workspace panel: application review/history, separate persona opt-in
  context, reason categories, account-code targeted invites/revoke, private roster,
  role changes/removal confirmations and audit. Hide/disable actions by role; server
  remains authoritative. No owner transfer, mobile management or private data.
- Workers may define exact local DTO interfaces initially; main generates and
  adds shared aliases after API integration. Use existing api/useSession/Feedback/
  useApiResource and PLM tokens; no shared CSS/session/navigation edits by workers.
- Main supplies app/organizations/page.tsx Suspense wrapper, Settings/event detail
  links, workspace integration and org-aware notification destinations. Four mobile
  tabs remain unchanged. Account changes must remount/abort private state.

### Exclusive worker writes

1. Membership backend: new memberships models/schemas/policy/applications/
   routes_applications/__init__.py and tests/memberships/test_applications.py ONLY.
2. Lifecycle backend: new memberships access.py/routes_access.py and
   tests/memberships/test_access.py ONLY. Request shared seam changes from main.
3. Attendee UI: the two MemberPortal files above ONLY.
4. Staff UI: the two StaffMembership files above ONLY.
5. Quality assessor: tests/shared/test_sprint8_quality.py and
   docs/validation/sprint8-quality-review.md ONLY; report production defects to main.
   Main assigns the serial PostgreSQL test slot; never reset the scratch DB in parallel.

Canonical notes were read, not edited outside the workspace. This is the agreed
implementation contract; execution evidence is recorded separately in the linked
acceptance report. Vault synchronization of the new decisions remains a handoff
item, not a claim that the canonical notes have already been updated.

## Completed local checkpoint

- All 294 backend checks passed against real isolated PostgreSQL; four opt-in
  browser tests then passed separately and serially (36 journey groups).
- All nine frontend contract checks, lint, TypeScript, isolated/normal static
  builds, credential guards and development schema drift checks passed.
- Reviewed additive `mvp_0006` is applied; existing development row counts were
  preserved across migration. The normal frontend/API and explicit deadline
  worker are restored. No Penpot, cloud or real-user data was used.
- Five Luna/max workers are closed. The main chat completed shared integration,
  regression fixes and independent acceptance. No separate Flash/fast control
  was exposed or claimed.

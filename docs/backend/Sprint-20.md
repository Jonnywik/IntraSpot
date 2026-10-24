# Sprint 20 — manual organization ownership transfer

## Scope and frozen contracts

Implement the accepted manual transfer, not automated inactivity succession.
Reuse approved-organization workspace and membership authorization. Only the
current active eligible owner may nominate a currently active eligible admin of
the same approved organization. The named admin must accept before seven days
have elapsed. Acceptance atomically changes owner -> member and admin -> owner;
both memberships stay active. Preserve `Organization.created_by` as historical
creator metadata, all participation, events and existing privileges unrelated to
ownership. No credential sharing, public member directory, admin override,
automatic deletion, succession scoring or mobile management.

API prefix `/api/v1`:

- `GET /organizations/{org_id}/ownership-transfers`: current owner sees recent
  organization history; a named nominee sees only their own offers. No guests,
  unrelated organizations, moderators or ordinary members. Bounded latest 100.
- `POST /organizations/{org_id}/ownership-transfers`:
  `{nominee_id: UUID, client_key: UUID}`. At most one pending offer per
  organization. Explicit revoke, decline or expiry is required before replacing
  it. Same creator/client key plus same org/nominee returns that offer without
  duplicating it; incompatible reuse is 409. A former owner can recover their
  own stored retry result after transfer, but cannot create a new offer.
- `POST /organizations/{org_id}/ownership-transfers/{transfer_id}/decision`:
  `{action: 'accept'|'decline'|'revoke', version: positive integer}`. Nominee
  accepts/declines, current owner revokes. The client captures the offer/version
  under review. Same-actor same-action original-version terminal retries are
  idempotent; conflicting actions/versions never reverse a completed decision.

`OwnershipTransferOut`: `id, org_id, from_user_id, nominee_id, status, version,
created_at, expires_at, resolved_at, decided_by`. Status is pending, accepted,
declined, revoked or expired. Server derives every actor/time/status. No emails,
persona text, arbitrary account lookup or client-selected expiry. Reads project
expiry without writes; mutations seal expired offers before admitting a new one.
Expiry is exact (`now >= expires_at`), including after restart. A decision checks
time again after acquiring locks. Recheck current roles, eligibility and active
memberships on accept; a stale signed-in role is not authority.

## Data and transactions

New `ownership_transfers` and `ownership_transfer_audits` tables. Request key is
unique per originating user. Pending org offer uniqueness is enforced by a
partial index. A partial unique index on active owner memberships enforces at
most one active owner per org; migration refuses inconsistent pre-existing data
without silently repairing it. Creation/transfer paths maintain exactly one.

Reuse the organization's existing row lock, then lock offer and affected
memberships in deterministic order. On accept, demote/flush the former owner
before promoting, within one transaction. Do not call leave/removal workflows:
they would incorrectly cancel event participation. Role history, immutable
transfer audit and deduplicated in-app notifications commit atomically with the
decision. No external emails. Audit actions: requested, accepted, declined,
revoked, expired. Every audit records server actor/time; expiry may use a null
actor. Membership audit action `ownership_transferred` records both role changes.

Additive `mvp_0015` follows `mvp_0014`, explicitly applied, never at startup.
Rollback refuses to erase transfer or audit data. Preserve all pre-existing
development rows in fictional and real profiles. PostgreSQL tests run serially.

## Interface and acceptance

Desktop existing organization workspace only. Current owners select a nominee
from the existing private staff roster, filtered to eligible active admins.
Nominees review their own offer, expiry and role consequences. Explicit in-page
confirmation, Cancel initial focus, keyboard/Escape/focus return, loading/error,
conflict refresh and stable retry payloads. No organization-management fetches
on mobile. Refresh server role/workspace after decision; former owner loses
management controls while keeping member participation. Notifications route to
the currently authorized workspace/club and use English/Filipino strings.

Verify wrong-role/cross-org/self/ineligible/inactive requests, role changes
before acceptance, exact expiry/restart behavior, simultaneous accepts/revokes,
duplicate retries, one-owner invariant, atomic audit/notifications and unchanged
registrations/chat access. Shared integration/migrations/generated types/tests
are coordinator-owned. Existing Sprint 18 browser and dependency-security gates
remain open; Sprint 20 must not imply those passed or authorize deployment.

# Sprint 8 local acceptance and handoff

Date: 2026-10-15 (Asia/Manila). Local implementation, serial regression gates
and normal runtime restoration passed. This is not deployment approval.

The main chat coordinated five non-overlapping GPT-6 Luna/max workers: membership
applications/invitations, lifecycle/roles, attendee UI, staff UI, and independent
quality assessment. All workers are closed. The tools exposed no separate
Flash/fast-mode control, so none is claimed.

## Implemented scope

- Approved public organization profiles and an attendee Clubs entry point, also
  reachable through mobile Settings without changing its four persistent tabs.
- Signed-in membership applications, including approval before PLM eligibility.
  A grant on file does not authorize member features, My Clubs, chat or staff
  workspaces until the trusted account meets their existing eligibility rules.
- Separate, unchecked-by-default consent to share nickname and interests during
  pending review only. No application note, email, age, pronouns or icebreaker.
- Owner/admin/moderator approval or predefined-reason rejection, with actual
  deciding account and server time. Rejection permits immediate reapplication;
  withdrawal starts a server-enforced 24-hour per-organization cooldown.
- Recipient-bound, seven-day, single-use in-app invitations with decline,
  revocation, expiry and compatible retry recovery. Forwarding cannot transfer
  access. Acceptance/reactivation grants member, never a former staff role.
- Private staff roster/audit, owner-controlled admin roles, admin-controlled
  member/moderator roles, hierarchical removal and non-owner self-service leave.
  Owner departure/removal/transfer is not enabled.
- Atomic departure effects: non-ended registrations end, waiters can be promoted,
  old active/archived chat access is revoked, and generic notices are persisted.
  Ended attendance remains historical. Immutable old admission receipts cannot
  recreate participation; a new public registration after departure is allowed.
- Desktop-only management, account-isolated frontend state, same-key uncertain
  response recovery, generated API types and organization notification links.

The full user choices and frozen cross-domain interfaces are in
[Sprint 8 contract](../backend/Sprint-8.md).

## Verification record

| Gate | Observed result |
| --- | --- |
| Complete serial PostgreSQL backend suite | 294 passed, four opt-in browser tests skipped, 299.09 s |
| Combined rendered browser suites | All four passed serially, 36 journey groups, 102.31 s |
| Sprint 8 browser gate | Nine groups passed in that combined run, including final cooldown copy |
| Earlier browser journey gates | Core: ten groups; approval/reconfirmation: eight; communication/safety: nine |
| Frontend contract tests | Nine passed after final API type regeneration |
| Frontend lint | Passed after final copy changes |
| TypeScript, static export and credential scans | Passed for isolated API 8002 and restored normal API 8001 builds |
| Development schema drift | No new upgrade operations detected |
| Normal local runtime probes | API health/readiness 200 with `mvp_0006`; frontend `/`, `/organizations`, `/workspace` 200; worker running |

The membership browser gate checks that historical rejection copy cannot
contradict a newer withdrawal cooldown. The combined run checks actual UI actions
and persisted PostgreSQL outcomes, not static substitutes. It also includes prior
API restart proof and five viewport checks. Browser tests are automated checks,
not participant validation. The latest `results.json` files and membership
screenshots are the passing evidence; older `failure.png` files are diagnostic
history, not a current failure.

One upstream Starlette/httpx deprecation warning and the existing frontend Node
module-inference warning remain non-blocking. No new dependencies were introduced
to conceal those warnings.

## Findings fixed during integration

- Ineligible accounts no longer receive new chat-activity notices or read/mark
  existing chat notices while ineligible. Current trusted eligibility is checked
  for inbox/thread/send; membership revocation applies to retained private chat.
- Explicit query roots remove ambiguous inbox/thread joins introduced by the
  additional access-revocation relationship.
- Expired invitation acceptance/decline returns a conflict, not a false success.
  Unknown/inactive invitees return a recipient-unavailable error, not a sender
  authentication failure. A compatible send retry still recovers its original
  invitation even if that recipient later becomes inactive.
- Departures preserve legacy registration orders even where no admission receipt
  exists. The event counter advances only; later registrations get a fresh order.
- Role changes, leave and removal send generic organization notices even where
  there are no event registrations. Operation retries do not repeat these effects.
- Application/invitation changes refresh the effective actor, so My Clubs access
  appears/disappears without another sign-in. A refresh failure does not repeat
  the successful mutation.
- Historical rejection copy explains that rejection itself adds no cooldown,
  rather than promising immediate reapplication despite a newer withdrawal.
- Test-harness corrections were kept distinct from product fixes: compare UTC
  instants rather than ISO spelling, create the SQLAlchemy session from its
  factory, and locate select controls by their rendered accessible names.

## Migration and data preservation

Explicit reviewed migration `mvp_0006` adds five membership tables and optional
organization notification context. It does not migrate at application startup.
Downgrade refuses to discard membership history, access revocations or
organization-context notifications. Preservation/refusal tests use only the
guarded scratch database.

The development upgrade preserved these existing aggregate row counts unchanged:
15 users, 9 organizations, 20 organization memberships, 15 events, 1 registration,
0 admission receipts and 0 notifications. No broad seed/reset was used. Its
pre-existing registration without a receipt motivated a dedicated regression.

## Runtime and reproduction

The restored normal runtime is frontend `http://127.0.0.1:3000` and loopback API
port 8001, with the explicit local deadline worker running every 30 seconds.
Unattended registration/report/chat/invitation deadlines need that worker; reads
or authorized actions also catch up relevant state. Live API health/readiness and
three frontend route probes returned 200. Static bundle verification found API
8001 and no test API 8002 reference.

The first normal-port rebuild encountered Windows `EPERM` creating a generated
Next build directory. No source fix or cache deletion was performed. The same
build passed outside the restricted shell, including TypeScript, prerendering
and credential scans. The exact Windows locking/permission source was not proven;
no OneDrive-specific cause is asserted.

PostgreSQL 17 remains in the dedicated local MVP database on loopback port 5433.
Tests reset only `intraspot_mvp_test`. No Penpot database, cloud service or real
account is involved. The browser harness starts/stops only its own API 8002 and
frontend processes; the normal frontend must be rebuilt for API 8001 afterward.

See [local setup and browser commands](../backend/README.md). Existing approved
organization fixtures are usable without a new seed: Fictional student 4 owns
Fictional Phase 2 Approved Organization; Fictional student 5 is its admin. Use a
different fictional account to apply, or share that account's displayed code for
an invitation. Tokens stay in the ignored backend manifest and expire after eight
hours; renew with the guarded local identity helper without publishing them.

## Limits and remaining release gates

- This is a local fictional-data MVP, not a real-user release. Participant testing,
  security/operational review and isolated cloud integration remain required.
- No succession, announcements, recommendation ranking, flash events, email,
  uploads, real sign-in, mobile management or Penpot changes were added.
- Ending membership locks that organization's published events in a stable order
  to keep cancellation, access revocation and promotion atomic. This deliberately
  favors correctness for the local pilot; larger-scale lock duration/load needs
  measurement before deployment. No throughput claim is made.
- Existing Sprint 7 chat tombstone/polling payload limits still apply. No infinite
  retention, production-scale pagination or background cloud service is implied.
- User decisions and implementation evidence are recorded in the repository.
  Canonical Obsidian notes were read but not edited outside the permitted workspace;
  synchronizing these new decisions into the vault remains a handoff item. Old
  unresolved notes are not authority to override the user's explicit choices.

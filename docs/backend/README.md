# IntraSpot local MVP

## Current work — Sprint 20 manual ownership transfer

Sprint 20 adds desktop-only nomination of an active eligible organization admin,
a seven-day acceptance deadline, decline/revoke, scoped history, and atomic role
changes. Acceptance makes the former owner a member without removing either
person's participation or chat access. Creator metadata is historical; current
membership roles remain authoritative. Audits and in-app notices are retry-safe.
Automated inactivity succession and mobile management are not included.

Reviewed additive `mvp_0015` follows `mvp_0014`; apply explicitly, never at startup.
The migration refuses duplicate active owners and destructive history rollback.
See the [contract](Sprint-20.md), [interaction handoff](../design/sprint20-interaction-handoff.md),
and [acceptance record](../validation/sprint-20-acceptance-2026-10-23.md).
Sprint 18's live-browser and existing Next.js dependency-security/build gates
remain open; Sprint 20 is not deployment or participant approval.

### Historical Sprint 18 checkpoint

Sprint 18 code is implemented locally: optional text-profile editing, explicit
broad/event-only sharing, scoped persona reads, mutual block hiding, outgoing
block management and an anonymous registration warning with explicit proceed.
Shared group-chat content and existing participation are preserved. Sprint 19
remains implemented. Explicit additive `mvp_0014` follows `mvp_0013`; all existing
development rows and Featured history were preserved.

Automated verification is recorded in the [acceptance report](../validation/sprint-18-acceptance-2026-10-23.md).
Live browser acceptance remains pending because the old in-app browser tab is an
inaccessible internal error page. The final build commands also stop on the
existing Next.js 16.4.0 security advisory; a minimal patch was requested, not
silently applied. No deployment or release approval. See the
[contract](Sprint-18.md) and [interaction handoff](../design/sprint18-interaction-handoff.md).

### Historical Sprint 17 checkpoint

Sprint 17 is complete locally: private saved events, My Events list/calendar,
and advisory confirmed-event overlap warnings. Saving never registers or reserves
a place. Both profiles use explicit additive `mvp_0012`, with pre-existing data
preserved. See the [contract](Sprint-17.md),
[acceptance evidence](../validation/sprint-17-acceptance-2026-10-20.md), and
[interaction handoff](../design/sprint17-interaction-handoff.md).

Developer checks passed; participant/native-device/security/release approval is
still separate. Personal Google sign-in is verified, live PLM sign-in remains
pending. Default fictional 3000/8001 and real-development 3001/8011 stay isolated;
no new cloud storage/SQL or deployment. Sprint 18 persona/blocking is next, not
implemented. Sprint 16 and 17 changes remain local/uncommitted until requested.

### Historical Sprint 16 checkpoint

Sprint 16 adds persistent local event banners and club logos, authorized upload,
replacement/removal, decoded validation, metadata stripping, and protected image
reads. Apply the reviewed additive `mvp_0011` migration explicitly; never migrate
at startup. Existing fictional and real-development data remain isolated. See the
[contract](Sprint-16.md), [acceptance report](../validation/sprint-16-acceptance-2026-10-19.md),
and [interaction handoff](../design/sprint16-interaction-handoff.md).

Personal Google development sign-in is now verified. Live PLM-account sign-in is
still pending; it is not implied by the personal-account check. Supabase remains
Auth-only; media and application SQL stay local. Default fictional 3000/8001 and
real-development 3001/8011 are separate. Sprint 17 saved events/calendar/conflicts
is next, not implemented here. No deployment or new GitHub push is part of Sprint 16.

### Historical Sprint 15 setup checkpoint

Sprint 15 is in progress, not complete. The selected Supabase development
project is connected; Google OAuth client/provider setup and live sign-in remain
pending. See the [project connection checkpoint](../validation/sprint15-project-connection-2026-10-19.md).
Supabase is used for Auth only; application data stays in a
separate local PostgreSQL database. No live Google or PLM-account pass has been
claimed. The normal fictional demo remains on 3000/8001; the separate real-auth
profile is designed for 3001/8011 and never uses fictional seed identities.
See the [verified local progress record](../validation/sprint-15-progress-2026-10-19.md),
[frozen contract](Sprint-15.md) and
[private-credential-safe setup guide](sprint15-setup-guide.md). Do not run the real
profile with placeholder project settings or describe mocked protocol checks as
live OAuth. Production/deployment and Sprint 16 remain out of scope.

### Historical checkpoint through Sprint 14

Sprint 14 organization announcements and reactions is complete locally
(2026-10-19). Public/current-member posts live in existing organization profiles;
approved owner/admin desktop workspaces manage versioned posts and history.
Readers use the same six aggregate reactions. A dedicated platform queue handles
announcement reports with exact bounded evidence, audited decisions and durable
expiry. Four mobile destinations and prior event/person rules are unchanged.
See [Sprint 14 contract](Sprint-14.md),
[acceptance evidence](../validation/sprint-14-acceptance-2026-10-19.md), and
[interaction handoff](../design/sprint14-interaction-handoff.md).
Apply the reviewed additive `mvp_0010` migration explicitly, never at startup.
Sprint 15 isolated real development sign-in is next, not implemented. This remains
local and fictional; participant/native-device/security/release checks and
long-term revision/deleted-content retention remain separate gates. No deployment
or commit/push was performed.

### Historical checkpoint through Sprint 13

Sprint 13 Flash events is complete locally (2026-10-18). The existing editor
supports Scheduled/Flash; Flash uses instant registration and a start within
24 hours of publication. Matching-area For You priority lasts three hours or
until start, inside existing club groups. The saved Show Flash events switch
defaults on and affects discovery only; existing participation stays available.
See [Sprint 13 contract](Sprint-13.md),
[acceptance evidence](../validation/sprint-13-acceptance-2026-10-18.md), and
[interaction handoff](../design/sprint13-interaction-handoff.md).
Apply the reviewed additive `mvp_0009` migration explicitly, never at startup.
Sprint 14 announcements/reactions is next, not implemented. This remains local
and fictional; participant/native-device validation and real-user release are
deferred. No deployment or commit was performed.

### Historical checkpoint through Sprint 12

Sprint 12 explainable For You discovery is implemented locally (2026-10-17).
Signed-in users default to server-ranked For You; guests keep Upcoming. Private
Settings inputs add optional broad-area and recurring Manila availability;
interests reuse Profile tags. Event drafts support optional public tags/area.
Search/My Clubs and explicit Upcoming/Newest still compose, and registration,
privacy and accreditation rules are unchanged. See [Sprint 12 contract](Sprint-12.md),
[acceptance evidence](../validation/sprint-12-acceptance-2026-10-17.md) and
[interaction handoff](../design/sprint12-interaction-handoff.md). The reviewed
additive migration is `mvp_0008`; apply migrations explicitly, never at startup.
Sprint 13 Flash events is next, not implemented. This remains a local fictional
MVP; participant/native-device validation and real-user release are deferred.

### Historical checkpoint through Sprint 11

Sprint 11 mobile attendee completion is complete locally (2026-10-17). The four
attendee destinations, focused mobile chat, profile feedback, saved registration
outcomes and safe-area sizing passed developer checks. See the
[Sprint 11 contract](Sprint-11.md),
[acceptance evidence](../validation/sprint-11-acceptance-2026-10-17.md), and
[interaction handoff](../design/sprint11-interaction-handoff.md). Sprint 12
explainable For You discovery is next, not implemented here. Participant and
physical-device checks remain deferred. No deployment or commit was performed.

### Historical checkpoint through Sprint 10

Sprint 10 desktop management, safe draft autosave and the organized inbox are
complete locally (2026-10-16). See [Sprint 10 contract](Sprint-10.md),
[acceptance evidence](../validation/sprint-10-acceptance-2026-10-16.md) and
[interaction handoff](../design/sprint10-interaction-handoff.md). The actual
desktop browser gate passed 18 groups, and the communication/safety regression
passed nine groups. Sprint 11 mobile attendee closure is next; participant review
remains deferred. No new database migration or deployment is part of Sprint 10.

The default profile uses fictional data on backend `127.0.0.1:8001` and frontend
`localhost:3000`. The separate real-development profile uses Supabase Auth on
3001/8011 with local application SQL/media. Neither profile has participant or
deployment approval. Penpot's database is not used.

## Setup (PowerShell, project root)

All commands below run through the project's RTK wrapper. Backend dependencies are pinned in `Code/Backend/uv.lock`; Python 3.14.7, FastAPI 0.142.2 and Uvicorn 0.54.0 are retained.

```powershell
Set-Location Code/Backend
rtk proxy uv venv .mvp-venv --python C:/Python314/python.exe --cache-dir .cache/uv
rtk proxy uv export --format requirements-txt --output-file requirements.lock --cache-dir .cache/uv --quiet
rtk proxy uv pip sync requirements.lock --python .mvp-venv/Scripts/python.exe --cache-dir .cache/uv --link-mode copy
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_setup
rtk proxy docker compose --env-file .env.local up -d --wait
rtk proxy .mvp-venv/Scripts/python.exe -m alembic upgrade head
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_identities
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_organizations
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_events
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_communication
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_flash
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_announcements
rtk proxy .mvp-venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log --log-level warning
```

Sprint 8 local membership lifecycle is implemented and verified as of 2026-10-15. The main chat coordinated non-overlapping Luna/max workers and independent quality review; all workers are closed. See [Sprint 8 contracts and decisions](Sprint-8.md) and [acceptance evidence](../validation/sprint-8-acceptance-2026-10-15.md). Earlier milestone notes remain historical acceptance records.

Sprint 9 desktop attendee polish and persistent preferences are complete locally
as of 2026-10-16. See [Sprint 9 contract](Sprint-9.md),
[acceptance evidence](../validation/sprint-9-acceptance-2026-10-16.md), and
[interaction handoff](../design/sprint9-interaction-handoff.md). Participant review
remains deferred; organizer/mobile follow-up sprints and deployment are not implied.

`app.local_identities` idempotently creates 15 fixed fictional User records only and generates ignored `Code/Backend/.local/accounts.json`, an array of `{label,token}` entries. Tokens expire in 8 hours. Rerun the same command to renew tokens; existing profiles and privileges are not overwritten. It accepts no user/subject arguments and rejects non-local or test-database execution. It creates no organizations, events or frontend files. Never publish the manifest or expose these services beyond loopback.

The old frontend public token manifest was moved recoverably into ignored `Code/Backend/.local/sprint5-quarantined-frontend-accounts.json`. Never restore it to public assets. The frontend uses an explicit local-demo flag and the guarded local backend catalog; its build scans public assets and static output for credentials. Do not reset data or invoke the broad `app.seed`.

## Local frontend

Use Node 26 (for helper tests) and the existing locked frontend dependencies.
In `Code/Frontend`, copy `.env.example` to ignored `.env.local` only if the latter
does not exist, then run `rtk proxy npm.cmd run build` and `rtk proxy npm.cmd start`.
Open `http://127.0.0.1:3000`. The static server binds only to loopback. Guest browsing
needs no account; select a fixed fictional account in the labeled local-MVP bar.
Tokens remain memory-only. Sprint 9 remembers only the selected fictional account
label in this tab's session storage; a hard reload obtains its existing local
catalog token and verifies `/me` again before restoring account preferences.
Continue as guest clears that remembered label. No token is stored in browser
storage, and this is not a real sign-in mechanism.

The backend must run on port 8001 after reviewed migrations. Renew expired local
tokens with `app.local_identities`; do not paste or publish them. The catalog is
available only in explicit local mode, to a loopback peer with an allowlisted host
and origin. It verifies the existing fixed signed catalog; it issues no tokens.

Frontend checks: `rtk proxy npm.cmd run lint`, `rtk proxy npm.cmd test`, and
`rtk proxy npm.cmd run build`. Regenerate reviewed API types with
`rtk proxy npm.cmd run api:types` after exporting the backend OpenAPI schema.

The opt-in browser gate uses the scratch database and port 8002. Build with
`NEXT_PUBLIC_API_URL=http://127.0.0.1:8002`, then run the backend test
`tests/shared/test_sprint5_browser.py` with `RUN_SPRINT5_BROWSER=1`. Do not run it
concurrently with other database tests, and keep port 3000 free. Rebuild with the
normal port 8001 afterward. The harness starts and stops only its own servers.

For the Sprint 6 browser gate, use the same isolated build and set
`RUN_SPRINT6_BROWSER=1` when running `tests/shared/test_sprint6_browser.py`.
These browser gates must run serially, not alongside other database tests.

For Sprint 7, use that same isolated build and set `RUN_SPRINT7_BROWSER=1`
when running `tests/shared/test_sprint7_browser.py`. It checks guest comments,
reactions, lost-response retries, confirmed-only chat, moderation, personal
restrictions, archived mobile chat and notification reads. These are automated
browser journeys, not participant validation.

For Sprint 8, use the same isolated build and set `RUN_SPRINT8_BROWSER=1` when
running `tests/shared/test_sprint8_browser.py`. It exercises membership requests,
approval-before-eligibility, temporary basic persona sharing, rejected-request
reapplication, withdrawal cooldown, targeted invitations, staff hierarchy,
departures, waitlist promotion, archived chat revocation and mobile navigation.

For Sprint 9, use the isolated build and `RUN_SPRINT9_BROWSER=1` with
`tests/shared/test_sprint9_quality.py`. It checks preference persistence, account
isolation, failed-save retries, Filipino interface text, system/dark themes,
reduced motion, keyboard sheets and responsive desktop sidebars. Run serially.

## Desktop preferences (Sprint 9)

Sprint 13 adds strict boolean `show_flash`, default true, to these private
preferences. Partial writes preserve it; old guest records/responses missing the
field default on. The discovery switch composes with search, sorting and My
Clubs through `include_flash=false` before pagination. It does not mute
notifications or hide public detail, My Events or chat. The additive local
Flash fixture helper never overwrites existing events or renews publication
times; create a fresh valid draft when an old fixture has ended.

`GET/PATCH /api/v1/me/preferences` stores only the current verified account's
language, theme, text size, high contrast, reduced motion and decoration pause.
Defaults are English, light, standard text and all three booleans false. A default
read creates no row; partial writes preserve other fields. Migration `mvp_0007`
is explicit and additive; rollback refuses to erase saved preferences.

Guest choices use a versioned browser-local record, never seed an account, and
can be reset if that record is corrupt. Signed-in saves are serialized, show
failure/retry feedback and remain scoped to their original account. System
reduced motion always overrides animation choices. User-written event/chat
content and organization names are not translated.

The accepted Quiet Heritage A layout uses existing authorized club shortcuts and
upcoming-registration data in desktop sidebars, retaining a single <=680px feed.
Three columns become two below 1180px and feed-only below 1000px. Mobile retains
the existing four tabs; dedicated mobile polish is deferred to Sprint 11.

## Club membership (local fictional demo)

Open **Clubs** on desktop, or **Settings → Clubs and membership** on mobile.
Guests can browse approved organization profiles. Any active fictional account
can apply; an approval can be recorded before PLM eligibility, but member features
and workspace access stay locked until the trusted account is PLM-eligible.
There is no browser button for changing eligibility or collecting a real email.

Existing fixtures include Fictional Phase 2 Approved Organization, owned by
Fictional student 4, with Fictional student 5 as admin. Use another sample account
that is not already a member to request access. Review on the desktop Organization
workspace. Existing staff or membership edits are not overwritten by this sprint.

Requests have no written note. Nickname/interests sharing is a separate unchecked
choice, ends with the review, and never exposes email, photos, age or pronouns.
Rejection includes a category and permits immediate reapplication; withdrawing a
pending request imposes a server-enforced 24-hour cooldown for that organization.

For an invitation, the intended user shares their own account code from Clubs.
The owner/admin enters that code in the desktop membership panel. No user directory,
email lookup or external mail is added. Invitations last seven days, are revocable,
and can only be accepted by the named account. Acceptance grants ordinary membership,
not staff access, and does not bypass eligibility. An old accepted invitation cannot
reactivate membership after departure.

Non-owners may leave. Owners/admins can remove members or moderators; only owners
can remove admins. Owners cannot leave or be removed while still owner. Role changes
replace the prior role, with admin grants controlled by the owner. Departures cancel
current organization-event participation, release/promote seats, and revoke retained
chat access without deleting ended attendance or rewriting original retry outcomes.
Departure does not create a permanent ban on otherwise-public registration.

## Organization announcements (Sprint 14)

Open the existing **Clubs** organization profile (on mobile: Settings → Clubs
and membership). Guests see approved organizations' public posts. Current
eligible active members can also read members-only posts. Six aggregate reactions
do not register attendance. Eligible signed-in readers can report accessible
content from another author; private receipts do not reveal retained evidence.

The desktop organization workspace gives approved eligible owners/admins
publish/edit/remove/history controls with explicit audience selection, protected
retries, version conflicts and load-older actions. Moderators/members do not
author. Platform admins use the separate announcement safety queue on desktop;
they do not gain ordinary member-only access solely from platform privileges.

After the explicit migration, `app.local_announcements` additively creates two
fictional samples in Fictional Phase 2 Approved Organization (Fictional student 4
owns it). Existing edits, roles, memberships, removals and history are preserved.
It accepts no arbitrary identities or content and refuses non-local/test execution.
Do not invoke the broad seed or publish the ignored fictional-account manifest.

Announcement reports retain exact open-case snapshots until the 14-day deadline
or decision, then purge them. Reporting never automatically hides or restricts
an author. Only the case that hid a post can restore it; removed posts remain
removed. The existing explicit deadline worker catches up expiry after restart.
Local revision history is not an approved indefinite production-retention policy.

For the Sprint 14 Edge gate, use the isolated API-8002 frontend export, renew the
ignored fictional catalog with the guarded helper, and set `RUN_SPRINT14_BROWSER=1`
while running `tests/shared/test_sprint14_quality.py`. Keep port 3000 free and run
database/browser suites serially. Rebuild for normal API 8001 afterward. These
automated checks do not constitute participant or native-device validation.

## Local communication and safety

After the reviewed `mvp_0005` migration, `app.local_communication` additively
creates Fictional Community Meetup. Fictional student 4 owns its organization.
No comments, reports, messages or registrations are fabricated by this helper;
interactions use the real local APIs and persist in the dedicated MVP database.
Existing event edits are preserved when the helper is rerun.

Guests can read comments. Eligible local accounts can use six reactions and
pre-start comments; reactions do not register or reserve a seat. Only confirmed
attendees can enter an event chat, including staff. Chat becomes read-only at
scheduled end, stays in the same inbox with an Archived marker/countdown, and
becomes inaccessible 72 hours later. The deadline worker physically removes
expired original messages and processes stored report deadlines.

Content reports go to organization staff first, with escalation to platform
review. Explicit personal reports go directly to the fictional platform admin.
Reporting does not automatically remove content; personal hide/restore affects
only the reporter. Open personal review pauses new comments/chat and event
creation/publication, not reading, reactions or existing seats. Resolution or
expiry restores those operations. All notifications remain generic and in-app.

## Approval review and deadline worker

After explicitly applying migrations, `rtk proxy .mvp-venv/Scripts/python.exe -m
app.local_approvals` adds one fictional approval event without resetting data.
Fictional student 4 owns its organization. Approval requests reserve seats;
organizer/admin/moderator review is desktop-only. Persona sharing is opt-in per
registration. Exact selected removals are the default for capacity reductions;
newest confirmations within a selected pool are an explicit alternative.

Run the deadline worker in a separate local terminal:

```powershell
rtk proxy .mvp-venv/Scripts/python.exe -m app.deadlines --interval 30
# A single restart catch-up pass:
rtk proxy .mvp-venv/Scripts/python.exe -m app.deadlines --once
```

Stored registration/report deadlines survive process restarts. The worker also
cleans up chat after its retention window. It must remain running for
timely unattended expiry; it is deliberately not started by API startup. Review
and attendee operations also perform authorized catch-up. Stopping the local
processes does not delete outcomes, but delays background processing until a
worker or relevant operation resumes. The runner rejects non-local/test settings.

## Verification

```powershell
# Code/Backend
rtk proxy .mvp-venv/Scripts/python.exe -m pytest -q
rtk proxy .mvp-venv/Scripts/python.exe -m alembic check
```

Shared fixtures reset ONLY `intraspot_mvp_test` after checking its actual database name and loopback target. Development data is never truncated. Migrations are explicit and never run during app startup. Keep secrets, `.local`, `.env.local`, dependencies and generated demo manifest ignored.

## Status

**Completed Sprint 8 (2026-10-15):** membership applications and temporary basic
persona consent, approval-before-eligibility with locked access, categorized
rejection/immediate retry, withdrawal cooldown, seven-day targeted invitations,
staff hierarchy, leave/removal and atomic attendance/chat consequences are
implemented. The complete backend suite passed 294 tests; all four rendered
browser suites passed serially (36 journey groups); nine frontend contract tests,
lint, builds, credential guards and migration drift checks passed. The frontend,
loopback API and 30-second deadline worker are restored. See
[Sprint 8 acceptance and limits](../validation/sprint-8-acceptance-2026-10-15.md).
Canonical vault synchronization remains a handoff item; participant/security
review still gates real-user release.

**Completed Sprint 7 (2026-10-15):** guest-readable comments, six mutually
exclusive reactions, confirmed-only polling chat with archive/72-hour retention,
personal hide/restore, role-isolated reporting/moderation, bounded evidence holds,
personal-review restrictions and durable in-app notification reads are implemented.
The full backend suite passed 257 tests, nine frontend contract checks passed,
and all three real-browser journey gates passed separately, including the final
desktop fit/restart check. Lint, builds, credential guards and migration drift
checks passed. See [Sprint 7 acceptance and limits](../validation/sprint-7-acceptance-2026-10-15.md).
The explicit local worker must remain running for unattended deadlines/cleanup.
Retained chat tombstone invalidation has a documented local-pilot payload limit;
participant/security review still gates real-user release.

**Completed Sprint 6 (2026-10-13):** approval registrations, reserved seats,
durable review extension/escalation, material changes/reconfirmation, and exact
default/optional pool capacity reductions are implemented. 205 PostgreSQL
regression tests, both real-browser gates, nine frontend contract tests,
build/lint/credential scans and migration checks passed. See
[Sprint 6 acceptance and handoff](../validation/sprint-6-acceptance-2026-10-13.md).
The explicit local deadline worker must remain running for unattended expiry.

**Completed Sprint 5 (2026-10-13):** 176 PostgreSQL regression tests, nine frontend
contract checks, and the opt-in real-browser journey/restart gate passed.
Static export, TypeScript, lint, credential scans and schema drift checks passed.
All four core journeys now use persisted FastAPI data. See
[Sprint 5 acceptance and handoff](../validation/sprint-5-acceptance-2026-10-13.md).
This local fictional-data MVP is not a real-user release.

**Completed Sprint 4 (2026-10-13):** **173 combined PostgreSQL checks passed**, including competing registrations/withdrawals, immutable retries, caller isolation, waitlist notifications, independent-process intake recovery and real HTTP API restart proof. A shared-user lock-order risk across event batches was fixed without changing receipt admission order. Schema drift and OpenAPI freshness checks passed. See [Sprint 4 acceptance and handoff](../validation/sprint-4-acceptance-2026-10-13.md). Sprint 5 frontend integration is next; real-user release remains blocked by participant/security gates.

**Completed Sprint 3 (2026-10-13):** 127 combined PostgreSQL tests passed; 10 live HTTP/restart check groups passed; OpenAPI was regenerated and schema drift checks passed. Drafts, approved publishing, public discovery, composed search/My Clubs/sorting, private/public counts and lifecycle boundaries were verified. A draft-era registration recovery privacy defect was reproduced and fixed atomically. See [Sprint 3 acceptance and handoff](../validation/sprint-3-acceptance-2026-10-13.md).

**Completed Sprint 2 (2026-10-12):** 85 PostgreSQL regression tests passed, the focused 8-test quality gate passed, and live application/accreditation/draft checks plus distinct-instance persistence verification passed. See [Sprint 2 acceptance](../validation/sprint-2-acceptance-2026-10-12.md). Participant/security release gates remain closed.

After generating the existing predefined identities, `rtk proxy .mvp-venv/Scripts/python.exe -m app.local_organizations` adds the fixed pending/approved/rejected fictional organizations and active memberships. It is local-only, additive and idempotent; it does not reset data or overwrite existing membership/decision edits. Approved/rejected fixture decisions use the actual fictional database admin and server timestamp. Do not invoke the broader `app.seed`.

Then `rtk proxy .mvp-venv/Scripts/python.exe -m app.local_events` adds one fixed incomplete pending draft and two approved scheduled/instant public events with fictional artwork keys. Existing edits/history are preserved on rerun; collisions and stale rejection are guarded. It creates no registrations and accepts no arbitrary arguments. Tokens remain in the ignored backend manifest, not frontend public files.

**Historical Sprint 1 verification:** Root independently ran `tests/identity` and `tests/shared/test_foundation.py`: **32 passed, 1 dependency deprecation warning in 10.46 seconds** (2026-10-11). This covers trusted fictional identities, token validation, database-derived eligibility/privileges, private self-profiles, local configuration/CORS, sanitized metadata logging, migration readiness, test isolation, and commit-before-success behavior. Identity organization-grant serialization is fixed with attribute-based response validation.

PostgreSQL 17 uses the separate `intraspot-mvp` project and `intraspot_mvp` database on loopback port 5433. Readiness requires the reviewed current head, `mvp_0013`: Featured requests, decisions and global placement-window exclusion. `mvp_0012` adds private saved events; `mvp_0011` adds local media; `mvp_0010` adds announcements/reactions/history; `mvp_0009` adds Flash and its saved discovery switch; `mvp_0008` adds discovery metadata/preferences; `mvp_0007` adds display preferences; `mvp_0006` adds membership lifecycle; `mvp_0005` adds communication/safety. Apply reviewed migrations explicitly with `python -m alembic upgrade head`; they do not run at startup. Downgrades refuse to discard retained feature history or other new data rather than silently losing it. Sprint 19 was explicitly selected before Sprint 18, which remains unbuilt. See [Sprint 19 acceptance](../validation/sprint-19-acceptance-2026-10-22.md).

**Historical Sprint 1 checkpoint:** at that stop, Sprints 2–5 and frontend were paused. Their existing code was preliminary, not accepted. Phase 2 now evaluates the organization domain and its draft/publication authorization boundary only; it does not accept all event/registration/notification code. Participant/security release gates remain closed.

Runtime checkpoint: local Uvicorn launched with `--no-access-log --log-level warning`; direct loopback probes of `/health` and `/ready` returned HTTP 200. Root independently passed 9 live HTTP checks: health/readiness 200; guest actor/profile and forged token 401; fictional student actor/profile 200 with no email disclosure and database-derived eligibility; self-profile PATCH 200 round trip; attempted platform-admin profile mutation 422. No secrets were printed. Two new identity-fixture tests were added after the 32-test gate; their execution is not included in that earlier result.

Final Sprint 1 checkpoint: **34 focused tests passed**, one upstream deprecation warning, in 9.77 seconds, including both identity-fixture tests. The 9 live HTTP checks passed again using the identity-only backend manifest. All agents are stopped and closed; Sprints 2–5 remain paused. The loopback API is available at `http://127.0.0.1:8001`. See `docs/validation/mvp-backend-acceptance-2026-10-11.md` for independent evidence and the scope override.

Dependency setup: original `.venv` could not be updated because Windows denied package-directory replacement. No destructive environment reset was performed. The isolated `.mvp-venv` successfully installed 37 locked packages using Python 3.14.7 with the requested FastAPI/Uvicorn versions. `requirements.lock` is exported from `uv.lock`; retain both for reproducibility. Frontend project-local installation also completed.

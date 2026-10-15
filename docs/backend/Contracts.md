# Local MVP contracts — 2026-10-13

User-authorized local implementation supersedes the prototype-only timing gate for fictional local testing only. Canonical Obsidian notes remain unchanged; participant/security validation still gates release.

## Current authorization — Sprint 6 (2026-10-13)

Sprint 5 frontend integration is complete. Implement approval registrations,
durable review deadlines/escalation, material changes and reconfirmation under
[Sprint 6](Sprint-6.md). Exact capacity selection is the default; the user also
authorized the explicit newest-in-selected-pool option. Coordinator owns
mvp_0003 expansion and mvp_0004 integrity migrations. Earlier authorization and
ownership sections below are historical, not the current stage. Cloud, chat,
membership lifecycle and real-user release remain deferred.

## Code review fixes — 2026-10-13

The preceding user-authorized repair pass preserved a 5% remaining-usage reserve and did not accept the full Sprint 4 or Sprint 5 deliverables. The subsequent next-sprint request now authorizes Sprint 4, as recorded below and in [Sprint 4 execution](Sprint-4.md).

- Public discovery/detail are read-only. Discovery supports `limit` (default 50, maximum 100) and nonnegative `offset`; confirmed counts are fetched in one grouped query for the page. Pending receipts are processed by registration writes and current-user recovery, not anonymous reads.
- Optional event summary defaults to an empty string and is capped at 200 characters in draft inputs and publication validation, including existing drafts.
- Migration `mvp_0002` requires published events to have title, description, start/end, venue name/address, positive capacity and artwork, with end after start. Drafts may remain incomplete. Upgrade validates existing rows without rewriting them; downgrade drops only the added check. Readiness requires `mvp_0002`.
- Withdrawal, earliest-waiter promotion and the promotion notification commit under one event lock in one transaction. Active confirmed and waitlisted registrations cannot withdraw at/after start. Repeated withdrawal of an already cancelled registration remains idempotent.
- `GET /organizations/{org_id}` exposes approved organizations only. Pending and rejected workspaces remain privately authorized.
- OpenAPI was regenerated after these changes. See [repair validation](../validation/code-review-fixes-2026-10-13.md) for current evidence; earlier sprint results remain historical.

## Ownership

The main chat is the coordinator. Sprint 4 uses four GPT-6 Luna/max workers with disjoint acceptance files defined in [Sprint 4 execution](Sprint-4.md): API boundaries, subprocess recovery, competing mutations and independent quality assessment. The coordinator owns production fixes and shared configuration/contracts/errors/database/migrations/dependencies/router/common frontend/API client/types/notifications. Earlier assignments are recorded in [Sprint 3 execution](Sprint-3.md) and [Phase 2 execution](Phase-2.md). There is no Sol coordinator subagent. Fast-mode selection is not exposed by the subagent tool and is not claimed. Frontend work remains deferred.

## Exact Python seams (frozen)

`app.db.session`: `Base` declarative base, `engine()` cached SQLAlchemy Engine, `session_factory()` returns synchronous sessionmaker(expire_on_commit=False), `get_db()` FastAPI generator commits successful route/rolls back failure. `app.db.models`: `uid()` UUID string, `now()` aware UTC datetime, `UTC` timezone-aware SQLAlchemy DateTime. No shared domain ORM classes.

WRITE-RESPONSE GATE: all write routes using `get_db` must declare `Depends(get_db, scope='function')`, or services explicitly commit before returning. Request-scoped teardown is not proof of persistence before the response. Registration owns its intake/drain commits. Shared pytest fixtures: `db` Session; `client` TestClient; `token_for(user_or_id, **claim_overrides)` signed token; `make_user(**fields)` returns complete eligible User; `make_org(owner=None, **fields)` returns approved Organization with owner membership; `make_event(org=None, **fields)` returns future published instant Event with capacity3. All factories commit so independent request connections see fixtures. All resets assert the dedicated test database first.

`app.core.errors.DomainError(code, message, status=400)` is the sole business error. `app.core.contracts.Actor` frozen dataclass fields `user_id:str,nickname:str|None,eligible:bool,profile_complete:bool,platform_admin:bool,grants:tuple[OrgGrant,...]=()`. `OrgGrant` fields `org_id,org_name,role,accreditation_status` all strings.

Identity worker implements `app.core.auth.current_actor()` required bearer dependency returning Actor, `optional_actor()` anonymous-or-valid Actor (invalid supplied token must fail, not become guest), `require_eligible()` returning Actor or DomainError403. Verify RS256 with settings public PEM/issuer/audience/expiry/subject; only `sub` selects DB User; eligibility uses DB verified email (root/subdomain policy). Inactive/missing users rejected. `User` ORM in `domains/identity/models.py`: table `users`; `id` String36 PK defaultuid, `email` String254 unique NOTNULL, `email_verified` bool defaultFalse, `active` bool defaultTrue, `platform_admin` bool defaultFalse, `nickname` String64 nullable, `age_bracket` String32 nullable, `tags` JSONB defaultlist, `pronouns` String40 nullable, `icebreaker` String300 nullable, `persona_visible` bool defaultFalse, `created_at` UTC defaultnow. No image/profile-public endpoints.

Organizations worker `domains/organizations/models.py`: `Organization` table `organizations` fields `id` String36 PK, `name` String200, `description` Text default'', `accreditation_status` String16 pending/approved/rejected defaultpending, `created_by` FK users.id, `created_at` UTC. `OrgMembership` table `org_memberships`: `id` PK, `org_id` FKorganizations.id, `user_id` FKusers.id, `role` owner/admin/moderator/member, `active` bool defaultTrue, UNIQUE(org_id,user_id). `AccreditationDecision` table `accreditation_decisions`: `id` PK, `org_id` FK, `outcome` approved/rejected, `admin_id` FKusers.id, `decided_at` UTC defaultnow. `service.require_manager(db,actor,org_id)->Organization` verifies eligible active owner/admin; `service.active_club_ids(db,actor)->list[str]`; `service.require_publishing(db,actor,org_id)->Organization` adds accreditationapproved. Moderator/member denied management in this scoped MVP.

Events worker `domains/events/models.py`: `Event` table `events`; `id` PK, `org_id` FKorganizations.id, `created_by` FKusers.id, `title` String200 nullable, `summary` Text NOTNULL default'', `description` Text nullable, `starts_at`,`ends_at` UTC nullable, `venue_name` String200 nullable, `venue_address` String500 nullable, `capacity` Integer nullable positivewhenpresent, `banner_key` String64 nullable (allowed heritage/design/garden/music), `cost_label` String100 default'Free', `status` String16 draft/published defaultdraft, `registration_mode` String16 defaultinstant, `event_type` String16 defaultscheduled, `interest_count` Integer default0, `next_admission` BigInteger default0, `created_at` UTC defaultnow, `published_at` UTC nullable. No relationships needed. Publish validates futurestart and end>start. Public detail projection described below. Public discovery/detail routes are read-only: they never call registration drain or mutate receipt outcomes.

Registrations worker `domains/registrations/models.py`: `RegistrationReceipt` table `registration_receipts`; `id` PK, `user_id` FKusers.id, `event_id` FKevents.id, `idempotency_key` String128, `event_order` BigInteger, `result` JSONB nullable, `http_status` Integer nullable, `created_at` UTC defaultnow, `processed_at` UTC nullable; UNIQUE(user_id,idempotency_key), UNIQUE(event_id,event_order). `Registration` table `registrations`; `id` PK, `user_id` FKusers.id, `event_id` FKevents.id, `status` confirmed/waitlisted/cancelled, `admission_order` BigInteger, `created_at` UTC defaultnow, `confirmed_at` UTC nullable, `updated_at` UTC defaultnow. Partial unique index(user_id,event_id) WHERE status IN ('confirmed','waitlisted'). `service.drain_event(event_id:str)->None` owns separate synchronous transactions, safe after restart/retry. Acquire transaction advisory lock derived user/key BEFORE event lock on intake; commit receipt counter increment + receipt, then drain Event lock orderedpendingreceipts. Routes use session_factory, not request db transaction for intake/drain.

Coordinator `app/notifications.py`: `Notification` table `notifications`; `id` PK, `user_id` FKusers.id, `event_id` FKevents.id, `registration_id` FKregistrations.id, `kind` String40 defaultwaitlist_promoted, `message` String200, `dedupe_key` String200 unique, `created_at` UTC defaultnow. `notify_promotion(db,registration)` inserts in same caller transaction; no commit. Worker imports this function only. `/me/notifications` current-user read.

All PK defaults uid and all timestamps now unless stated. UUID values are strings (route UUID validation may normalize str). Check constraints for enumeratedstates/positivecounts. Coordinator imports all models in migrationenv after workers create them. Agents export `router` from their `app.domains.<domain>.routes` with prefix-less `/api/v1` paths relative to coordinator prefix; do NOT include `/api/v1` themselves.

## Exact HTTP/frontend seams (frozen)

- Identity: `GET /me` -> `{id,nickname,eligible,profile_complete,platform_admin,grants:[{org_id,org_name,role,accreditation_status}]}`; `GET/PATCH /me/profile` -> `{nickname,age_bracket,tags,pronouns,icebreaker,persona_visible}`. PATCH forbids extra fields, requires boundedvalidfields, supports partialupdate.
- Organizations: `POST /organizations` body `{name,description?}`; `GET /organizations/{org_id}` public; `GET /organizations/{org_id}/workspace` manager; `GET /me/organizations` activegrants plusownedworkspaces; `GET /platform-admin/organizations` admin applicationlist; `POST /platform-admin/organizations/{org_id}/accreditation-decision` body `{outcome:'approved'|'rejected'}`. Org response `{id,name,description,accreditation_status,created_at}`; workspaceadds`role,decisions:[{id,outcome,admin_id,decided_at}]`. Adminlist includesdecisions.
- Events: `GET /events?q=&sort=upcoming|newest&my_clubs=false` -> array EventPublic; `GET /events/{event_id}` publishedonly; `GET /organizations/{org_id}/events` private drafts/publiclist; `POST /organizations/{org_id}/events` nullableDraftfields; `GET/PATCH /events/{event_id}/draft` private; `POST /events/{event_id}/publish`. Public `{id,org_id,organization_name,title,summary,description,starts_at,ends_at,venue_name,venue_address,capacity,confirmed_count,remaining_spots,interest_count,banner_key,cost_label,status,published_at}`. Draft sameoptionalfields pluscreated_by/created_at onlyprivate. No cancel endpoint, PATCH draft rejectspublished.
- Registrations: `POST /events/{event_id}/registrations` no body, required Idempotency-Key -> `{id,event_id,status,waitlist_position:int|null,waitlist_message:str|null,admission_order:int}`. `GET /me/registrations` -> array currentresult plus`event_title,starts_at,ends_at,organization_name,is_past:bool`. `DELETE /events/{event_id}/registrations/me` idempotentwithdraw -> currentresult(cancelled or existing cancelled); denies afterstart. No registeredotherusersprojection. Coordinator `GET /me/notifications` -> array `{id,event_id,kind,message,created_at}`.
- Frontend workers export default components at `features/identity/Profile.tsx`, `features/organizations/Workspace.tsx`, `features/organizations/Admin.tsx`, `features/events/Discover.tsx`, `features/events/Details.tsx`, `features/registrations/MyEvents.tsx`, and named `RegistrationAction` from `features/registrations/RegistrationAction.tsx` taking `{event:EventPublic}`. Details takes `{eventId:string}`; other components no props.
- Shared frontend `lib/api.ts`: `api<T>(path:string, options?:RequestInit):Promise<T>` with `/api/v1` base and currentbearertoken; `ApiError` has `.code,.status,.message`; `dateTime(value:string)` Manila formatter. `lib/auth.tsx`: `useAuth()` -> `{actor:Me|null,loading:boolean,error:string|null,refresh:()=>Promise<void>}`; shared `AuthProvider`/fictionalaccountselector ownedcoordinator. API currenttoken is sessionStorage key`intraspot-token`, neverconsolelogged; switching triggersactorrefresh. Generatedtypes in `lib/api-types.ts`; stable aliases `EventPublic,Me,Profile,Organization,Workspace,RegistrationResult,MyRegistration,AppNotification` reexportedfrom`lib/types.ts` coordinator. Workers can use interfaces duplicatedlocallyonlyuntilgeneratedtypesready, thencompileagainstshared.
- Parent runtime target backend`http://127.0.0.1:8001`, frontend`http://localhost:3000`; static eventroute`/events?eventId=...`, `/profile`, `/my-events`, `/organizations`, `/admin`. Coordinator supplies pagewrappers/header/auth/css. Allworkerforms useexplicitlabels; managementcomponents desktop-only wrapper, mobile4tabsprovidedbycoordinator. Workerfrontend starts ONLY after backend milestonetests pass and coordinator saysgo.

## Frozen interfaces

- `/api/v1/me` returns actor id, nickname, eligibility, profile completeness, platform-admin flag and active organization grants; never public email. Actor derives from verified RS256 local session subject and database identity, not body/metadata claims.
- `/api/v1/me/profile` is self-only. Nickname, age bracket and >=1 interest/vibe tag complete registration prerequisites. Persona hidden by default; no cross-user persona/image endpoint.
- Organization profile is public name/description/accreditation. Workspace is eligible owner/admin-only for MVP. Owner/admin can draft; approved accreditation gates publish. Decision actor/time derived server-side; rejected applications immutable.
- Event draft is nullable/incomplete; publish validates structured title/start/end/venue name/address/description/capacity/fixture banner. Instant/scheduled only. Published edits/cancellation are unavailable. Public event projection contains no attendee identities.
- Draft privacy boundary: registration intake increments the event counter only for a published row. `registrations.service.reject_draft_receipts(db,event_id)` terminalizes legacy unfinished private-event attempts with their rejected retry outcome in the caller's transaction; event publication invokes it while holding the draft row lock, before changing status. No timestamp inference or new registration workflow is introduced. Capacity input is bounded by PostgreSQL Integer storage; publishing compares aware times as UTC instants.
- Search title and organization name; Upcoming orders start/id, Newest publication/id. My Clubs is eligible active-member-only and composes with search. Active discovery excludes ended events.
- Registration requires eligibility/profile completeness and event start in future. `Idempotency-Key` 8–128 ASCII characters scoped to user and operation/event; same key + different event is 409. Original result is immutable, even after cancellation/promotion; fresh My Events returns current state.
- Intake first commits a receipt under the event counter lock. This durable admission sequence is the explicit platform receipt point, not network arrival or lock acquisition FIFO. Ordered drain locks the event and processes pending receipts in bounded batches of 200, preserving receipt order across transactions. Crash recovery occurs on submit, withdrawal or current-user listing, not anonymous public reads. No client order is accepted.
- One active registration per user/event. Different-key duplicate returns the existing current registration without consuming a seat. Withdrawal before start promotes earliest queue entry and creates a unique durable notification in the same transaction.
- UTC aware timestamps; Asia/Manila frontend display. Stable errors `{error:{code,message},request_id}`. Validation omits submitted values. Logging only correlation/action/outcome/internal IDs; no bodies/tokens/emails.

## Local configuration and boundaries

Separate PostgreSQL 17 compose project/database/volume on `127.0.0.1:5433`. Never touch Penpot database. Explicit Alembic upgrade; no startup migrations. Local fixture JWT keys/tokens/env ignored. Configuration rejects fixture auth outside local/test and rejects non-loopback/non-IntraSpot local database targets. Frontend demo selector only with explicit local build flag; account tokens generated locally into ignored fixture file. No cloud service/service-role keys, real identity data or external delivery.

Approved UI: fixed 72px nav, centered max1200px workspace, ~680px single-column feed, ivory/white/burgundy/navy/blue/gold, Noto Serif Georgian headings and Inter Tight UI. Four mobile tabs, no mobile management. Unsupported chat/social/approval/material-change/media/member-request features visibly unavailable.

## Milestone gates

CURRENT AUTHORIZATION (2026-10-13): following the Sprint 3 acceptance and repair pass, the user requested the next sprint. Complete and verify **Sprint 4: capacity-safe registration and waitlists** under [Sprint 4 execution](Sprint-4.md). Sprint 5 frontend integration, later roadmap features, cloud services and real-user release remain deferred. Preserve existing local data and migrations.

COMPLETED CHECKPOINT: Sprint 4 passed 173 combined PostgreSQL checks, including
real HTTP restart proof, with one upstream deprecation warning. Batch users
are locked in ascending User.id order before unchanged receipt-order decisions
to avoid cross-event lock inversion. See [Sprint 4 acceptance](../validation/sprint-4-acceptance-2026-10-13.md).

CURRENT CHECKPOINT: [Sprint 3 passed](../validation/sprint-3-acceptance-2026-10-13.md): 127 combined tests and 10 live HTTP/restart groups. No migration/dependency changes. All agents are closed; stop until the user authorizes the next sprint. This is local backend acceptance, not participant or deployment approval.

1. Foundation/auth: migration, configuration, forged/expired/wrong issuer/audience/subject and profile privacy tests.
2. Organization: creation/role isolation/pending draft and decision audit tests.
3. Events: drafts/publish boundary/public search and lifecycle tests.
4. Registration: PostgreSQL independent-connection races, retry/order/recovery/withdrawal/promotion/notification tests.
5. Integration: frontend build/type/lint and backend four-journey API tests. Parent independently validates browser presentation/interaction. Never label these participant tests or deployment approval.

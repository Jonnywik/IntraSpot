# Sprint 15 — isolated Google development sign-in

Authorized 2026-10-19: next roadmap sprint only. No deployment, real PLM
verification claim, Penpot, media/Sprint 16, commit/push or fictional-data reset.
The user needs help creating a separate Supabase development project. Live OAuth
acceptance remains pending until they configure it and complete sign-in privately.

## Isolation and shared contracts

- Preserve the current fictional frontend/API/database on 3000/8001/
  `intraspot_mvp`; its tests remain in `intraspot_mvp_test`. Never copy fictional
  accounts, privileges, memberships, posts or registrations into real development.
- Real development uses loopback frontend 3001, API 8011, and separate local
  PostgreSQL `intraspot_real_dev` (tests: `intraspot_real_dev_test`) on 5433.
  Supabase supplies Auth only in this sprint, not application database/storage.
  No connection to a Supabase PostgreSQL database or use of its database password.
- `Settings.auth_provider`: `fixture` default or `supabase`. Production remains
  disabled. Fixture requires FIXTURE_AUTH=true and the existing two DB names.
  Supabase requires FIXTURE_AUTH=false, local/test only, the two real-development
  DB names, HTTPS single-project *.supabase.co URL and `sb_publishable_` key.
  Only explicit loopback 3001 CORS origins in real mode. No shared signing secret,
  service-role/admin key, custom issuer/JWKS from a request, or fixture fallback.
- New settings: `supabase_url`, `supabase_publishable_key` (not repr),
  `supabase_issuer` derived as URL + `/auth/v1`; existing JWT fixture fields stay.
  `INTRASPOT_CONFIG=real` loads ignored Backend/.env.real.local. Missing/unknown
  profile or invalid configuration fails closed, never changes default .env.local.
- Real identity UUID is the verified Supabase subject in the separate DB, using
  existing User schema. No email-based identity merge and no schema migration.
  Existing migrations are explicitly applied to the new empty DB, not at startup.

## Backend identity seam (worker owns new module only)

`app.domains.identity.supabase_auth` exports:

- frozen `VerifiedSupabaseIdentity(user_id: str, email: str, email_verified: bool)`.
- `verify_supabase_identity(token: str, settings: Settings) -> VerifiedSupabaseIdentity`.
- `provision_supabase_user(db: Session, identity: VerifiedSupabaseIdentity) -> User`.
- `actor_from_supabase_token(db: Session, token: str, settings: Settings) -> Actor`.

Verify signature with installed PyJWT/cryptography and project-derived JWKS only;
allow ES256/RS256, bounded nonempty kid, exact issuer, authenticated audience/role,
expiry, iat, UUID subject/session_id, nonanonymous session. No Google provider
token, anonymous/anon/service-role token or token-selected jku URL is accepted.
Use bounded cached PyJWKClient and timeouts; fail closed with generic 401 for
invalid credentials, generic 503 for unavailable trusted Auth. Never log tokens,
emails, provider response content or error object bodies.

Fetch the authenticated current user from configured `/auth/v1/user` using the
verified access token and publishable apikey, HTTPS, no redirects, bounded body
and timeout. Match its id to subject; require a Google identity and nonanonymous
user. Trusted email and confirmation come ONLY from top-level Auth `email` and
`email_confirmed_at`, never user_metadata or browser flags. Ignore metadata roles,
profiles and eligibility. A confirmed personal email may sign in but is ineligible;
existing exact PLM-domain policy decides privileged product access.

New users have no profile, hidden persona, no grants and platform_admin=false.
Provision with concurrent retries/unique identity safety; a different subject
claiming an existing email fails without account linking/disclosure. Existing
profile fields, grants, admin flag and inactive state are preserved. Only trusted
email/confirmation synchronize; inactive accounts remain denied.

Run provisioning/synchronization in a short SEPARATE identity transaction before
domain authorization; do not hold User write locks while later domain operations
take organization/event locks. Then load the active user in the request Session
and reuse actor_for_user. Invalid tokens create no rows. Successful verified
onboarding may persist even if a subsequent domain operation is forbidden.

Coordinator dispatches existing `_actor_from_authorization` by configured provider
after parsing bearer; guest optional reads remain network-free. Real mode cannot
serve fictional catalog or execute fixture helpers/broad seed.

## Frontend seam (worker owns new auth files only)

Use official pinned `@supabase/auth-js` 2.118.0 (coordinator owns install/lock).
No hand-coded OAuth/token exchange. Google OAuth PKCE, minimal identity scopes,
fixed same-origin `/auth/callback`, no arbitrary next/returnTo destinations.
Only run on explicit real mode at localhost/127.0.0.1:3001 with API 8011 and matching
public project URL/publishable key. Fixture mode never initializes the real client.

Exports: `lib/real-session.tsx` -> `RealSessionProvider({children})`;
`features/identity/GoogleSignIn.tsx` -> `GoogleSignIn()`; callback is a static
`app/auth/callback/page.tsx`. Helpers in `lib/supabase-auth.ts` (optional own pure
helper files). Coordinator supplies shared `lib/session-types.ts` exporting
SessionContext and Session interface matching current fields plus
`signInWithGoogle(): Promise<void>`. Real provider must supply selectAccount as an
unavailable operation, never a fixture path. Existing useSession imports remain.

Keep access/refresh/provider tokens and Auth user objects in memory only. Persist
ONLY a bounded, expiring PKCE verifier through same-tab sessionStorage, clearing
on use/cancel/logout. Use a custom SDK storage adapter: verifier-key suffix maps
to one project-scoped expiring sessionStorage slot; other values use an in-memory
map. SDK `persistSession:true` is necessary for its custom adapter. Give each
client instance a fresh random storageKey so SDK BroadcastChannels cannot transfer
memory-only sessions across tabs; the adapter's verifier slot is independent of
that random prefix. Verify the pinned SDK's actual storage behavior with tests.
No real session restore across a hard reload in this narrowly scoped dev sprint;
restart Google sign-in then. Do not silently introduce localStorage token storage.

Capture/scrub code/error URL parameters before exchange, even for denied/error
callbacks; no arbitrary provider error descriptions or credentials in UI/logs.
Handle cancellation, missing/expired verifier, invalid code, backend denial and
unavailable network with generic recoverable feedback. SDK auto-refresh keeps the
same account version, but a changed account/logout remounts private page state.
Use the existing cancellable before-account-change guard for explicit sign-in/
sign-out; prevent stale promises from restoring a logged-out session. Never await
SDK calls inside onAuthStateChange synchronously; defer server actor verification.
Only send session.access_token to existing api(), never provider_token.

GoogleSignIn uses useT() with new `lib/auth-messages.ts` dictionary. Explain
development-only, personal-account ineligibility, no auto admin/membership,
profile completion and memory-only reload behavior. No real email shown in header.
Existing four mobile destinations and approved styling remain unchanged.

## Coordinator-owned integration

Configuration and provider dispatch; session-types/session wrapper and header
switch; environment examples and explicit real bootstrap; DB creation/migrations;
dependency lock; isolated frontend output `out-real`/3001 launcher; i18n assembly;
test infrastructure, generated API freshness, docs and canonical handoff.
Default exported `out` remains fictional; real builds must not overwrite it.
Static server no-referrer policy protects callback codes; no query/access logging.
Existing metadata-only logs remain unchanged.

## Non-overlapping Luna/max workers

1. Backend verifier/provisioning: new supabase_auth.py and
   auth_tests/test_supabase_auth.py only; no shared config/auth/routes/models.
2. Frontend auth: new files listed above, own optional helper/CSS files and
   tests/sprint15-auth*.test.mjs only; no existing session/header/i18n/package edits.
3. Independent QA: auth_tests/test_identity_boundary.py, own test helper modules
   (not conftest), docs/validation/sprint15-browser-check.mjs and quality notes.
   Read-only other files; report defects rather than edit another worker's files.

All workers read this contract; use RTK, apply_patch and preserve dirty work.
Coordinator owns all DB/browser tests; workers must NOT run those suites.

## Acceptance and stop

Prove wrong-project/expired/forged/wrong-role/Google-provider/fixture tokens fail;
metadata cannot confer eligibility or privileges; trusted email changes and
deactivation remain safe; concurrent onboarding does not duplicate or merge.
New real account has private incomplete profile and no roles; ineligible personal
account can browse but not register/social/workspace. Empty real DB has no fixture
catalog or seeded privileges. Preserve all fictional regressions/data/runtime.
Browser proof must distinguish mocked protocol/error tests from live Google
sign-in; only the user enters credentials. Record personal-account result and
live PLM verification as separate gates. Do not call Sprint 15 complete until the
live external dependency is verified; if absent, hand off implementation plus
exact setup blocker. Stop before Sprint 16 or any public deployment.

# Sprint 15 follow-up — development project connected

Status: **project connected; Google OAuth client/provider and live login pending**.
This supersedes the earlier checkpoint where project creation was still pending.
Sprint 15 is not complete.

## Connected and verified

- User selected Supabase project `qtlxfsfmjpyaymysqgds` (“Jonnywik's Project”) and
  supplied its public publishable key. The key was accepted by the project's
  public Auth settings endpoint. Compatible ES256 public signing keys were read
  from its configured-project JWKS endpoint.
- Supabase is **Auth only**. No cloud SQL/storage, Auth user administration,
  service-role key, project password or Google client secret was accessed.
  The browser's combined API-key panel was safety-blocked; no workaround was
  attempted. The user provided only the needed public key directly.
- Bootstrap created separate local `intraspot_real_dev` and ignored Backend/
  Frontend `.env.real.local` files. Existing reviewed migrations were explicitly
  applied to `mvp_0010`; no startup migration or fictional seed was run.
- Real application database has zero users and zero organizations. Its frontend
  is `http://127.0.0.1:3001`; API is `http://127.0.0.1:8011`. Both are running and
  ready. User-visible discovery correctly shows no events rather than fake data.
- Default fictional frontend 3000 and API 8001 still return 200/readiness.
  Real API `/me` rejects missing/invalid credentials with 401, the fictional
  account catalog returns 404, and discovery returns an empty list with explicit
  3001 CORS. No real user or registration was created.
- Both real config paths are ignored and untracked. Real static build/types and
  export credential guard passed. Browser check showed the isolated label,
  correct four mobile destinations and empty public feed. One fixture-only
  welcome hint was made conditional on auth mode, preserving the fictional copy;
  frontend/localization tests now pass **77/77**. Diff whitespace check passed.
  Focused lint on the two changed frontend files also returned exit 0.

## Historical external setup checkpoint (superseded below)

The live public Auth settings and dashboard both show **Google disabled**;
email sign-in remains enabled by the project's default settings. No cloud Auth
settings were changed. There is no successful OAuth or live PLM-eligibility
claim. Do not weaken verification or substitute email/fictional login.

The user requested help creating a Google OAuth client. Google Cloud opened in
the unrelated existing “hermes” project, which was not modified. A new-project
form was opened and its name filled as **IntraSpot Dev**; **Create was not
submitted**. The browser tab is handed off for the user to create/select the
separate Google development project, then configure its OAuth consent/client.
No Google OAuth client or credentials have been created or inspected.

Use minimal identity scopes, a Web application client, and this project's
Supabase callback `https://qtlxfsfmjpyaymysqgds.supabase.co/auth/v1/callback`.
The local app's callback is instead `http://127.0.0.1:3001/auth/callback`; configure
the matching Supabase Site URL/redirect allowlist during the private provider
setup. Client secrets must be entered directly by the user in Supabase, never
in chat, local frontend files or tracked evidence.

No unrelated Google/Supabase projects, billing, cloud schemas, deployment,
Penpot, commit/push, Sprint 16, participant testing or real-user release.

## Follow-up: live callback failure and safe diagnostics

The user created the separate `intraspot-dev` Google project/client and configured
the provider privately. The initial live authorization error was explicitly
`Unsupported provider: missing OAuth secret`; after the user supplied the secret,
public Auth settings confirmed Google enabled and the public key accepted, with
ES256 available. The user reports configuring the 3001 callback allowlist and
Google test user, then selecting their account and approving Google access.
These configuration changes were user-controlled; no client secret was read.

The app returned to `/auth/callback` but displayed the generic failure. Local
`intraspot_real_dev` still had zero users during the read-only check. This does
not establish the cause: a provider callback error, PKCE exchange rejection, or
local verification failure still needs a fresh observed attempt.

With explicit user approval, added finite, predefined callback diagnostic codes.
Raw error messages, callback codes, tokens, emails and arbitrary provider fields
are not rendered or logged. Provider errors in URL fragments are now detected as
well as query errors; both are scrubbed before any exchange. Existing memory-only
session storage, verifier cleanup, single-exchange protection and authentication
rules are preserved. Frontend tests pass **78/78**, including returned/thrown
exchange failures, query/fragment errors, verifier cleanup and private-text
non-disclosure. Live Google success and PLM eligibility remain unverified.

The isolated real build completed (including TypeScript and exported-asset
credential guard); the first sandboxed attempt hit a generated-folder Windows
EPERM, and a host-permitted rerun passed. A live callback reload displayed
`callback_code_missing`, expected because the prior URL had already been
scrubbed; this is not evidence of the original OAuth failure. The existing tab
was returned to Discover for a fresh user-controlled sign-in. No default demo
build, database, backend rule or cloud setting was changed by this diagnostic
patch.

The next user-controlled attempt reported `provider_rejected`. A read-only
inspection of that attempt's Supabase Auth `/callback` error confirmed the
upstream Google response: `invalid_client`, with the explicit message that the
provided client secret is invalid. No authorization codes, client secrets,
account details or raw log payloads are included in this evidence. The required
next action is user-controlled correction of the Google client ID/secret pair
in Supabase; no application-code change or security bypass is indicated by
this failure. Provider credentials were not opened or modified by the agent.

After the user corrected credentials privately, live IntraSpot showed `Google
session active` and the isolated local database contained one identity. The
user reports completing the profile and sign-out/sign-in check, and identifies
the account as personal, not PLM-issued. A read-only local identity-policy check
confirmed active/verified identity, complete profile, PLM eligibility false,
platform-admin false, zero effective organization grants, and persona visibility
false. Only boolean/count summaries were emitted; no email, token, ID or profile
content was printed. This verifies the personal-account policy state, not a live
PLM account, registration-denial journey or participant/release gate.

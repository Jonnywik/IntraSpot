# Sprint 15 development sign-in setup

Status: the selected Supabase development project is connected. Google OAuth
client/provider setup and live sign-in are pending; see the
[connection checkpoint](../validation/sprint15-project-connection-2026-10-19.md).
Passing local tests does not mean a Google account has signed in successfully.

## 1. Create a separate project (user controlled)

1. Open the [Supabase dashboard](https://supabase.com/dashboard) and sign in.
2. Create a new project named **IntraSpot Dev**, separate from production or any
   unrelated project. Review the displayed plan/cost before confirming. Do not
   enable a paid plan as part of this setup without making that choice yourself.
3. Set and save its database password privately. The IntraSpot integration does
   **not** need that password: application tables remain in local PostgreSQL.
4. When the project is ready, find its HTTPS project URL and public
   `sb_publishable_…` API key. Those are the only project settings needed by the
   local integration. Never share an `sb_secret_` key, service-role key, database
   password, Google client secret, access token or refresh token in chat.

## 2. Configure the Google provider (user controlled)

Follow the current [Supabase Google setup guide](https://supabase.com/docs/guides/auth/social-login/auth-google)
for the actual dashboard labels; they can change.

- Use a separate Google Cloud development project. Configure the OAuth audience,
  app branding and test users. Keep testing access limited to intended developer
  accounts, with only `openid`, email and profile scopes. No Gmail, Drive or
  other Google data permissions are needed.
- Create an OAuth **Web application** client. Its authorized redirect URI is the
  HTTPS Supabase project's `/auth/v1/callback`, copied from the Supabase Google
  provider settings. It is **not** the local application's callback URL.
- Enter the client ID and secret directly into the Supabase Google provider
  settings yourself; enable that provider. Do not put the secret in frontend
  environment files or this repository. Disable other sign-in providers for
  this narrow development project where possible.
- In Supabase Auth URL configuration, set the local Site URL to
  `http://127.0.0.1:3001` and allow the exact redirect
  `http://127.0.0.1:3001/auth/callback`. Use this same host throughout testing;
  changing between `localhost` and `127.0.0.1` changes the browser storage origin.
  Do not use a wildcard redirect or a public deployment URL.
- Confirm Supabase uses an **asymmetric signing key (ES256 or RS256)**. This
  backend intentionally does not accept legacy HS256 tokens or a shared JWT
  signing secret. See [signing keys](https://supabase.com/docs/guides/auth/signing-keys).

## 3. Configure the local application (coordinator can do this)

The explicit `app.real_setup` helper accepts the public project URL and
publishable key. It preserves `.env.local`, checks existing `.env.real.local`
files before any changes, and creates only the named local application database
if absent. It neither seeds fictional identities nor runs migrations.

Use the existing Backend virtual environment, with the normal fictional
configuration selected, to run the helper. Then explicitly select
`INTRASPOT_CONFIG=real`, apply the reviewed Alembic migrations to the newly
created `intraspot_real_dev`, and start the loopback API on **8011**.

From Frontend, `npm run build:real` reads its ignored `.env.real.local` and
produces `out-real`. `npm run start:real` serves that output on loopback **3001**.
The normal `out` export and fictional frontend/API on **3000/8001** stay separate.
The real build must be rebuilt if its public project settings change.

Never point either profile at Supabase SQL or move real identities into the
fictional database. Do not run fixture seed/setup helpers in the real profile.
Production configuration, public hosting and public network bindings remain
disabled. This setup does not approve billing or deployment.

## 4. Verify live, without recording credentials

1. Open `http://127.0.0.1:3001`, confirm the isolated-development label and click
   **Continue with Google**. Enter credentials yourself on Google's page.
2. Complete the same-tab callback. The local API must return the account with a
   private, incomplete profile and no administrative or organization grants.
3. With a personal Google account, verify public browsing works and PLM-only
   actions remain forbidden. Complete a minimal test profile only if desired.
   A personal-account pass is **not** proof of live PLM eligibility.
4. Verify profile changes persist in the separate local application database,
   sign out, and ensure private UI disappears. Refreshing the page requires a
   new sign-in in this deliberately memory-only development implementation.
5. Recheck the original fictional demo. Record only pass/fail, generic errors
   and non-identifying observations. No token dumps, account emails, callback
   codes, passwords or full OAuth responses in evidence/screenshots.

The [PKCE code](https://supabase.com/docs/guides/auth/sessions/pkce-flow) is
short-lived and single-use. A missing verifier, abandoned login, denied consent,
expired code, unavailable provider or backend denial must produce a generic
recoverable error, not a claimed successful sign-in. Start a new sign-in when
the callback cannot be reused. Avoid devtools network exports containing tokens.

## Remaining gates

- Actual user-controlled Google sign-in against the configured project.
- Actual eligible PLM-account verification when an account is available.
- Participant/native-device validation, security/release review and deployment
  approval remain separate. This sprint does not authorize public release.
- Local sign-out is immediate in the UI, but access-token revocation at an
  external provider is not guaranteed to be instantaneous. The backend checks
  signatures and the trusted Auth user; do not describe this as universal instant
  logout or revocation across devices.

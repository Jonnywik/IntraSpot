# Sprint 24 PLM sign-in verification

> User-run handoff checklist for the existing isolated local profile. This document is preparation only; no live PLM sign-in was performed.

## Current user-run result and deferral

On 2026-10-24, the user confirmed sign-in at port 3001. After the verified-session
indicator was built, they reported `Not eligible for PLM-only actions.` A private,
read-only aggregate check found one active real-development identity with a
verified email and zero trusted PLM-domain matches. No address, user ID or token
was printed, and no eligibility field or provider configuration was changed.
This confirms the non-PLM result, not a positive PLM sign-in pass. The user then
explicitly deferred further live PLM checking. Keep the positive PLM gate open;
do not prompt again during this sprint or inspect their provider callback.

## Scope and credential boundary

- Use the existing frontend at `http://127.0.0.1:3001` and its isolated API at `http://127.0.0.1:8011`. Keep this separate from the fictional profile on ports 3000/8001.
- The user selects the Google account and completes provider consent directly. Never put an email address, password, one-time code, access/refresh token, OAuth code, cookie, or unredacted provider/API response in chat or saved evidence. Use labels such as `A: personal` and `B: PLM`; redact account names and addresses from screenshots.
- A first verified `/api/v1/me` request can provision a local development profile. Do not submit registrations, comments, reactions, membership requests, or role changes for this check.

## What existing automation establishes

- [supabase_auth.py](../../Code/Backend/app/domains/identity/supabase_auth.py) verifies the configured Supabase token and obtains identity/email-confirmation data from the trusted Auth user response. [service.py](../../Code/Backend/app/domains/identity/service.py) makes eligibility depend on a confirmed email whose domain is `plm.edu.ph` or a subdomain; [auth.py](../../Code/Backend/app/core/auth.py) denies ineligible gated requests.
- Synthetic cases in [test_supabase_auth.py](../../Code/Backend/auth_tests/test_supabase_auth.py) cover signed test tokens, trusted-versus-editable identity fields, malformed/provider responses, and new-account defaults. [test_identity_boundary.py](../../Code/Backend/auth_tests/test_identity_boundary.py) asserts that a new verified PLM identity is eligible but incomplete, private, and has no admin/grants; a personal non-PLM identity can browse a public event but receives 403 for registration; and `/me` responses/action logs omit raw email and token.
- [sprint15-auth.test.mjs](../../tests/sprint15-auth.test.mjs) covers isolated-profile configuration, in-memory session storage, PKCE/callback scrubbing, session guards, and safe diagnostics. These tests do not contact Google or prove that a real PLM account can sign in. The Sprint 23 checkpoint records 50 synthetic-auth checks; that is prior automated evidence, not this live gate.
- Canonical policy: Obsidian `Functionality.md` → current account eligibility; `Security & Operations.md` → authentication and privacy; `System Architecture.md` → identity boundary; `Open Questions.md` → real PLM sign-in dependency. The current handoff still lists live PLM verification as open.

## User checklist

1. Confirm the address bar is the loopback frontend on port 3001. Start Google sign-in from IntraSpot and complete it yourself in Google's account chooser. Do not share the chooser or credentials.
2. **A — personal/non-PLM Google account:** sign in and confirm public event browsing works while the account is ineligible for PLM-only actions. Record only the booleans `signed_in`, `eligible`, and `public_browse`; expected: `true`, `false`, `true`. Do not submit a gated write. If the interface does not expose eligibility, use only a user-inspected, sanitized `/api/v1/me` result and retain `eligible` only.
3. Sign out through IntraSpot before switching accounts.
4. **B — PLM Google account:** sign in directly with the account you control. Confirm `/api/v1/me` succeeds and reports `eligible=true`; never record the address. For a newly provisioned local identity, expect `profile_complete=false`, `persona_visible=false`, `platform_admin=false`, and no organization grants. Inspect `/profile` without completing or saving it; the required fields are nickname, age bracket, and at least one interest/tag, and the persona starts private.
5. If this PLM identity already has a local development profile, report its current completion/visibility/role state as existing state. Do not reset or edit it to force the new-account defaults. Do not count any pre-existing admin role or membership as a sign-in grant; compare only whether the sign-in added privilege. If that comparison is unavailable, mark the privilege check inconclusive.
6. Keep the evidence to: run label (`A`/`B`), date/time, local profile (`3001/8011`), whether `/me` verified, `eligible`, `profile_complete`, `persona_visible`, `platform_admin`, grant count/delta, public-browse result, and pass/fail/blocked/inconclusive. Save no raw response, email, account/user ID, token, callback URL/code, or credential-bearing screenshot.

### Expected interpretation

- Personal Google authentication may succeed. The expected denial is `eligible=false` and no PLM-only access; it is not a Google sign-in failure.
- PLM eligibility is a separate result from profile completion. A fresh PLM identity may be `eligible=true` while registration remains blocked until its profile is completed. Do not treat that profile gate as failed PLM eligibility.
- A successful provider redirect alone does not prove the local API verified the account. A 401, network error, or API-unavailable message is not a PLM pass. Stop and record the run as blocked/inconclusive if `/me` cannot be verified or if new privilege appears unexpectedly.

## Source-level auth UI issue

Not live-observed: [GoogleSignIn.tsx](../../Code/Frontend/features/identity/GoogleSignIn.tsx) displays “Google session active” whenever a token exists. In [real-session.tsx](../../Code/Frontend/lib/real-session.tsx), a non-401 `/me` failure retains that token while clearing the actor and showing an API-verification error. Treat the status label alone as insufficient; require a successful `/me` result. The same sign-in control has no positive `eligible=true` label, while guest onboarding says “Sign in with an eligible PLM Google account” even though personal Google accounts may sign in for public browsing. This can make the eligibility split unclear; it does not establish a live auth failure.

## Sprint 24 auth-feedback implementation addendum

- `GoogleSignIn` now shows “IntraSpot session verified” only when an actor exists and auth is neither loading nor errored. It shows distinct pending and failed verification statuses, while preserving the existing token-based sign-out and retry controls.
- After successful `/me` verification, the visible controls row reports the server-derived PLM eligibility state. It does not display the email. The source-level status-label issue above is fixed; the onboarding-copy ambiguity remains for the main UI follow-up.
- Focused rendered-component coverage: `rtk proxy node --test tests/sprint24-auth-feedback.test.mjs` — 3 tests, 3 passed, 0 failed, 0 skipped. It covers pending/stale actor, API-unavailable and 401 failures, retry/sign-out controls, verified eligible/ineligible states, email non-disclosure, and Filipino translations. No browser or provider flow was exercised.
- Real PLM sign-in remains user-dependent and unverified.

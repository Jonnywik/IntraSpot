# Sprint 15 isolated-auth QA review

## Scope and mock boundary

`Code/Backend/auth_tests/test_identity_boundary.py` exercises the API actor and
domain boundary against the coordinator-provided `client`, `db`, `make_user`,
`make_org`, and `make_event` fixtures. Its verifier stub returns only the
frozen `VerifiedSupabaseIdentity`; it does not emulate JWT verification, JWKS,
Supabase Auth user lookup, Google OAuth, or any external service. The tests
cover private/incomplete onboarding, public event browsing versus protected
registration, preservation of existing account state, collision denial without
merge/disclosure, deactivation, fixture/foreign-token rejection, fictional
catalog isolation, and token/email exclusion from actor responses and action
logs. Malformed fixture/foreign tokens are expected to fail before a JWKS
lookup. Worker-owned `test_supabase_auth.py` contains the crypto and trusted-Auth
protocol coverage; QA did not run it.

## Coordinator implementation review (rechecked; gates pending)

The previously noted truncated-response issue is resolved in the current
implementation: `_trusted_auth_user` maps `http.client.HTTPException` (including
`IncompleteRead`) to the generic provider-unavailable response without returning
the partial body. Deeply nested trusted-Auth JSON also maps to that generic
failure. The worker-owned verifier now uses a 3-second timeout, a 256 KiB JWKS
body bound, a no-redirect opener, and a 300-second JWKS-set cache; per-key
caching is disabled. Corresponding worker tests are present, but were not run
by QA.

The frontend fixes called out during review are also present in source: the
callback route is not keyed/remounted on session-version changes, while other
private route content remains version-keyed; `/me` verification uses a
generation/user/token guard so a late response cannot restore an actor after
logout. The sign-in config is browser-resolved and bounded to the isolated
local origins and public publishable-key format. The compact header keeps
eligibility/profile/safety notices inside its collapsed “About development
sign-in” disclosure, with no raw email in the header. The callback page itself
is a section inside the shell's single `<main>`, not a nested main element.

These are source-review findings only. Coordinator-owned configuration,
integration, DB, frontend, and browser runs remain the validation authority; no
gate is marked passed here.

## Browser protocol boundary

`docs/validation/sprint15-browser-check.mjs` is authored but not run. It starts
and stops the coordinator-built `out-real` static server on
`127.0.0.1:3001`, loads the pinned Supabase Auth JS SDK from that build, and
strictly intercepts the fictional Auth origin and API at `127.0.0.1:8011`.
Synthetic authorize/token/logout and API replies are routed in-browser; other
external origins are blocked and counted. Its protocol cases cover persisted
PKCE verifier use, cancellation, token-exchange failure, backend denial,
reload (memory-only session), and a delayed `/me` retry racing with logout.
The mocked API actor is private/ineligible with an incomplete profile and no
admin or organization grants; `/me` must receive the Supabase access token,
never provider tokens. The success case verifies notice text is present but
hidden while its `<details>` disclosure is closed, then visible after opening.
The logout-race case checks DOM presence (not only visibility), so collapsed
details cannot conceal stale eligibility UI. Scoped cleanup must remove only
the project PKCE slot and preserve an unrelated test-owned `sessionStorage`
entry. Browser storage, URL, visible body text, and diagnostics are scanned for
synthetic credentials and the mock email. This is a protocol harness only: it
does not prove live Google authentication, Supabase cryptography, trusted Auth
user lookup, backend provisioning, or real PLM eligibility.

## Checks and limits

QA performed read-only source review and authored the integration test, browser
harness, and this report. No pytest, database test, migration, API/browser gate,
frontend build, package installation, or real external request was run. The
coordinator must build/run the frontend and run DB/browser gates in the assigned
serial slots. The user's private Google sign-in and live PLM eligibility
acceptance remain separate, unverified gates.

## Coordinator verification after QA handoff — 2026-10-19

The coordinator ran the real PostgreSQL synthetic-auth suite (50 passed),
existing backend regression (477 passed; 10 opt-in browser gates skipped),
frontend contracts/localization (76 passed), lint/types, both static builds,
and byte-for-byte fictional-export preservation. The final Edge protocol
harness passed all five groups with no unexpected Auth/external requests;
desktop/mobile fit and the actual fictional-app smoke also passed. Evidence
and exact remaining dependencies are in `sprint-15-progress-2026-10-19.md`.
These runs do not change the live Google/PLM gate from pending to complete.

# Sprint 15 progress — isolated Google development sign-in

Status: **in progress; local implementation verified, live setup pending**.
This is not a completed live-OAuth, participant or real-user release record.

Follow-up: [the development project is now connected](sprint15-project-connection-2026-10-19.md).
The checkpoint below records the earlier state before project setup; Google
OAuth client/provider creation and live sign-in still remain pending.

The user needs help creating a separate Supabase development project. No real
project settings have been provided and no actual Google account has signed in.
Stop before Sprint 16; follow the [setup guide](../backend/sprint15-setup-guide.md).

## Implemented slice

- Default fictional frontend/API/database remain 3000/8001/`intraspot_mvp`.
  Real development is separately configured for 3001/8011/`intraspot_real_dev`.
  Supabase supplies Auth only, never application SQL/storage. Real application
  DB/config are **not yet created**; only synthetic `intraspot_real_dev_test`
  was created/migrated for testing. No fictional identities/grants are copied.
- Explicit public-settings bootstrap preserves existing configs and never seeds
  or migrates automatically. Fixture helpers reject real mode. Invalid/mixed
  settings fail closed; production and fixture fallback remain disabled.
- Configured-project ES256/RS256 verification, exact issuer/audience/role,
  expiry and UUID subject/session; trusted Auth top-level email/confirmation,
  never editable metadata. Bounded no-redirect fetches, generic errors and
  300-second JWKS-set refresh with no indefinite per-key cache.
- Private incomplete onboarding with no automatic admin/membership grants,
  preserved existing profiles/grants/deactivation, no email-based merging, and
  short separate provisioning transactions to avoid adding a domain lock cycle.
- Official Auth JS 2.118.0, fixed same-origin PKCE callback, URL scrubbing,
  memory-only tokens/Auth users and expiring project-scoped same-tab verifier
  storage. Real browser credentials can reach only the separate 8011 API.
- Compact English/Filipino controls, safe retry/logout, stale-result/event
  guards, hydration and StrictMode-safe exchange. Callback avoids account-version
  remount; private pages keep that boundary. Four mobile tabs are unchanged.
- Separate `out-real` build, no-referrer/no-store static responses and export
  guards against signed credentials, private keys, Supabase secret keys and
  Google client secrets.

The main chat coordinated three non-overlapping Luna/max workers: backend,
frontend and independent QA. Coordinator owned shared seams/infrastructure,
dependency lock, i18n, serial database/browser gates, runtime and handoff. Workers
were closed after handoff. Existing dirty Sprint 9–14 work was preserved.
Graphify navigation was verified against canonical notes; Obsidian handoff,
roadmap and security notes now record **in progress**, not complete. No graph
export/rebuild was run.

## Observed verification

| Gate | Final result |
|---|---|
| Existing PostgreSQL regression | **477 passed, 10 opt-in browser gates skipped**, 637.89 s |
| Separate synthetic auth/PostgreSQL suite | **50 passed**, 13.76 s; real ES256/RS256 crypto, mocked provider, concurrency/provisioning/privacy APIs |
| Frontend/localization | **76 passed**, 3.72 s |
| ESLint / TypeScript | Passed; no rule suppression added |
| Default and isolated static builds / credential guards | Passed |
| Isolated build preservation | Fictional export preserved byte-for-byte |
| Final Edge auth protocol | Five groups passed; zero unexpected external/Auth requests; **Auth/API intercepted, not live OAuth** |
| Auth viewport checks | 1280 and 390 px; no horizontal overflow, one main region, four mobile destinations |
| Actual default API/Edge smoke | Guest discovery, existing fictional sign-in/out, mobile navigation/fit, no persisted bearer token passed |
| OpenAPI / model-schema comparison | Reviewed API unchanged; no new upgrade operations or migration |
| Runtime | Default frontend 3000 and restarted fixture API 8001 ready; deadline worker unchanged; synthetic 3001 server stopped |
| Whitespace | Passed |

XML: ignored `Code/Backend/.cache/s15-fictional-regression.xml` and
`s15-isolated-auth.xml`. Config/setup checks are included in the 477 count.
Synthetic browser evidence: `sprint15-browser-evidence/summary.json` and two
explicitly synthetic callback images. Independent review:
`sprint15-quality-review.md`. Earlier opted-in browser suites were not all rerun;
this sprint's protocol/default smoke are not every historical browser journey.

Initial checks reproduced and fixed malformed-JWKS/deep JSON error mapping,
callback remount, delayed logout/refresh, hydration/effect cleanup and frontend
type/lint issues. Results above are after those corrections.

## Remaining gates and known limits

1. User creates the isolated project and reviews the shown cost/plan. Passwords
   stay private. Only its public URL and `sb_publishable_…` key are needed locally.
2. User configures Google OAuth/provider and redirect allowlist privately.
   Explicitly bootstrap/migrate the separate local DB and rebuild using actual
   public project settings. Never serve the synthetic build as configured live.
3. Verify actual user-controlled personal Google sign-in. Record live PLM-account
   eligibility separately; it remains pending. Never record real email/token/code.

Runtime npm audit had zero known advisories at check time. Full audit retains
five high findings in the existing development-only eslint-config-next/
fast-glob/micromatch/braces chain, including
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
No forced framework downgrade was applied. This is not a security-release pass;
backend dependencies were not comprehensively security-audited. Existing
non-failing Starlette TestClient and Node module-type warnings remain.

Reload intentionally requires another sign-in; local logout does not promise
instantaneous universal external JWT revocation. Rate limits, participant/native
device validation, security/release review and unresolved retention remain
separate gates. No deployment, Penpot sync, reset, commit/push or Sprint 16 work.

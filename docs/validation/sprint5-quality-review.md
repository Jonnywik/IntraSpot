# Sprint 5 Quality Review

Reviewed the Sprint 5 brief and the frontend API, session, and domain flows. The only code change from this review is the Manila date validation fix; coordinator-owned findings are recorded here.

## Finding

### P2: API paths can escape the `/api/v1` prefix

`Code/Frontend/lib/api.ts:21-22` checks that a path starts with `/` and does not start with `//`, but it accepts dot segments and their encoded forms. The request at `Code/Frontend/lib/api.ts:34` concatenates the accepted path after `/api/v1`. Node 26 URL parsing resolves `/../me`, `/%2e%2e/me`, and `/%2E%2E/me` to `/api/me`, outside the frozen version prefix.

The current callers inspected build paths from fixed route names and encoded resource IDs, so this is a shared-helper boundary defect rather than a demonstrated external-input exploit. If an untrusted path reaches `api()`, its optional bearer token can be sent to a different route on the same local backend. The loopback-only origin check prevents sending that token to a remote host. `api.ts` is outside this review's edit scope, so this finding is report-only.

## Security checks

Coordinator resolution: the API helper now rejects literal/encoded dot segments,
backslash normalization and fragment paths before any fetch. The independently
rerun frontend contract gate passes all 9 tests (2026-10-13).

- The API client restricts its origin to HTTP loopback, uses `credentials: 'omit'`, and disables caching.
- Session tokens remain in React memory. Account changes and sign-out invalidate older account-selection responses; private resource data is keyed by token and cleared while a new key loads.
- The local fictional-account catalog requires the explicit build flag and a loopback browser hostname.
- The admin page does not hide its route based on `actor.platform_admin`; authorization remains server-side. The FastAPI service checks current database state, eligibility, active status, and the platform-admin flag for both listing and decision actions. Existing backend tests cover forged token privilege. Those backend tests were not run in this review.
- No unsafe HTML insertion, browser storage, cookie access, or console logging patterns were found in the inspected frontend source.

## Verification

- Node `v26.7.0`; `rtk node --test tests/sprint5-contract.test.mjs`: 8 passed, 1 failed. The failure is the existing API path-prefix rejection test, which reports “Missing expected rejection” for an accepted traversal path. The date validation test passes.
- No full test suite, lint, or build was run while parallel workers may still be writing.
- Node emitted a non-fatal `MODULE_TYPELESS_PACKAGE_JSON` warning while importing the frontend TypeScript helpers directly; the tests executed under Node 26.

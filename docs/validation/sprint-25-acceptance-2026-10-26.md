# Sprint 25 acceptance — 2026-10-26

Developer implementation checkpoint; hosted/provider and release gates remain open.

## Executed proof

- Default PostgreSQL regression: **728 passed, 11 opt-in browser skips**,
  zero failures, 1345.51 seconds. This sweep was collected before the last
  permission guards; the final focused run below covers those changes.
- Final hosted configuration/permissions: **45 passed**, zero failures/skips,
  13.77 seconds. Includes project-matched migration TLS, fixture denial, pool
  isolation, inherited/replication/schema ownership rejection, actual runtime
  `CREATE TABLE` denial and existing/future browser grant boundaries.
- Frontend suite: **156 passed**, zero failures/skips. Six hosted cases were
  rerun after tightening DNS-label validation; all six pass.
- Separate synthetic Supabase authentication suite: **50 passed**, zero failures
  in 19.48 seconds. This is protocol evidence, not a live PLM sign-in.
- ESLint and standalone TypeScript: passed. Existing module-type/deprecation
  warnings are not suppressed or represented as failures.
- Final hosted static export: **14 pages**, credential guard passed. A clean,
  ignored staging copy excluded dotenv/identity files; only its Turbopack root
  was adjusted to include the installed-dependency junction. The first staging
  build failed on that junction boundary; the corrected build passed. CI uses
  normal installed dependencies in a clean checkout.
- Root Docker image built from the frozen lock; a short-lived, disconnected
  check verified UID 10001, runtime imports, and absence of dotenv/local identity
  directories. The image was rebuilt with the final permission guards.
- npm dependency audit: zero known vulnerabilities, including dev dependencies.
- Tracked-delivery check passed. No dependencies/locks were changed.
- Original-column aggregate proof: both development datasets unchanged,
  **41 tables/76 fictional rows** and **41 tables/2 real-development rows**.
  Tests use disposable named databases; no production data or credentials used.

## Corrections during verification

The initial focused run passed 138 cases and failed one new pool test because it
reused the cached hosted engine when checking local configuration. Fix the test
cache lifecycle, not the local pool. A later new migration test supplied a CA
argument twice; correct the helper merge. The final 45-case run passes. The first
frontend run passed 155/156; add the missing Filipino hosted-footer translation.
QA additionally caught unvalidated migration credentials and privileged runtime
role/schema ownership cases; these are fixed and independently covered.

## Limits

Cloud Data API disablement, real hosted role/bootstrap/TLS/OAuth, required branch
checks and provider availability are not established by local SQL/URL tests.
No cloud deployment, paid resources, data import, media cutover, PLM verification
or participant/device/screen-reader testing occurred. CLI GitHub authentication
is unavailable; the connected GitHub app remains available for repository/CI
inspection. Remote workflow status is recorded after push, not guessed here.

The deadline runner and local disk media remain explicit dependencies of Sprints
26–27. Existing historical generated browser artifacts remain local and excluded.

The first GitHub frontend run passed 155/156 but exposed a cross-platform static
server boundary difference: an encoded backslash was rejected on Windows and
treated as a missing filename on Linux. Reject backslashes/NUL before filesystem
resolution on every platform; preserve the existing 400 assertion. This is a
Sprint 25 CI follow-up, not a skipped or weakened test.

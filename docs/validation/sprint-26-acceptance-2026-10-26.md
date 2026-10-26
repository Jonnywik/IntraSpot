# Sprint 26 acceptance — 2026-10-26

Developer checkpoint for private storage/accounting. Real cloud setup, participant
validation and release approval remain open. [Implementation](../backend/Sprint-26.md).

## Executed evidence

- Final affected PostgreSQL suite: **76 passed**, zero failures/skips, 68.27s.
  Covers media access, immutable writes, failed-write charges, quota admission,
  public-bucket rejection, secret/header handling, read outages, dry-run sightings,
  missing/protected objects, migration preservation, pool concurrency and config.
- Fresh-process persistence: **1 passed**, 15.94s. A terminated writer's ledger
  and local bytes are read by a second interpreter. This is not a live Supabase
  availability claim; remote HTTP behavior is checked with protocol fakes.
- Six-thread/five-connection bounded-pool check passed. Authorized reads reuse the
  existing session; three hosted request slots reserve two connections for durable
  media accounting. No local pool-size reduction.
- Frontend existing suite: **156 passed**. New media UI: **4 passed** (worker's
  combined focused media run covers ten). Lint and standalone TypeScript pass.
- Reviewed OpenAPI export and generated frontend types updated for media errors.
- Additive `mvp_0018` applied explicitly to both isolated development schemas;
  original 41-table values match (76 fictional rows, 2 real-development rows).
  The two new fictional ledger rows are expected backfill of the two original
  media assets. No images or original metadata were rewritten.
- Alembic drift check: no new upgrade operations. Default reconciliation command
  demonstrated dry-run output with no deletion or quota release.

## Failures and source corrections

An earlier affected run passed 73/74; first upload in the replacement test returned
an unexpected storage 500. That case passed subsequently. Do not claim its exact
cause was proven. Independently, source review found a reservation finalization
race with reconciliation; finalization is now idempotent and has its own regression.
The final wider suite passes. Metadata/storage outages are now sanitized 503s.

Review also found nested read sessions could consume the hosted pool while holding
parent sessions. Reuse the authorized session and reserve hosted connection
capacity; the bounded-pool concurrency test verifies progress. Missing objects
are not falsely treated as absent references, and confirmed missing unreferenced
objects can age through observations while remaining charged.

## Explicit limits

No bucket, administrator key, cloud SQL or real OAuth configuration was changed.
Hosted startup requires privately supplied Storage configuration and a private
bucket; direct provider access must be checked before cutover. Supabase's new
secret keys use `apikey`, not bearer JWTs ([official key guidance](https://supabase.com/docs/guides/getting-started/api-keys)).

This sprint does not delete objects or release orphan charges. Sprint 28 must
revalidate current references/holds and implement guarded cleanup; until then,
ambiguous reservations remain conservatively charged. Do not schedule the
unbounded operator reconciliation scan inside the request loop. Human/device/
screen-reader and positive live PLM gates remain deferred and unclaimed.

## Remote CI follow-up

Run 40326335393 at b153409: frontend passed; backend returned 721 passes, 30 failures and 11 opt-in browser skips. Twenty-seven failures used hard-coded pre-upgrade migration expectations; three media visibility mocks did not accept the new request-session keyword. These are corrected in the following checkpoint with affected suites rerun. This run is not recorded as green.

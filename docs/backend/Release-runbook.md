# Controlled evaluation release runbook

This runbook prepares a controlled evaluation. Public exposure, spending and
general-public release require separate approval. Koyeb Free can sleep; do not
send artificial keepalives or describe the free instance as production suitable.

## Before any hosted change

- Select a committed revision with passing CI and a completed release ledger.
- Obtain actual participant, physical-device and screen-reader evidence; resume
  positive PLM verification only when the user asks. Keep unmet gates visible.
- Configure an empty isolated hosted dataset, private Storage bucket, exact HTTPS
  origins and exact OAuth callback. No local account or fixture import.
- Disable the Data API; restrict application grants and future grants. Keep Auth
  and Storage managed tables untouched. Verify the runtime role cannot change
  schemas and browser roles cannot read application data.
- Use verified TLS to the session pooler. Runtime and migration credentials are
  separate. Start one API worker with the reviewed 3+2 connection budget.
- Configure off-provider encrypted weekly database-and-object backups, four
  restore points, separate key custody and current erasure-ledger preservation.
  A database backup alone does not preserve object bytes. Verify the scheduler
  and recovery alert; a powered-off laptop is not a reliable hosted backup job.

## Promotion order

1. Freeze writes for the recovery point and export the current erasure ledger.
   Make and verify a paired premigration backup; retain its manifest and hashes.
2. Review every additive migration against the currently deployed application.
   Run it explicitly with the migration role. Never migrate at API startup.
3. Start the selected API artifact with hosted-only validation, one worker,
   trusted-edge boundary, private media and background maintenance enabled.
4. Check liveness and readiness, then authorized operational status. Verify
   guest discovery, private-data denial and the core journeys with consented
   evaluation identities. Health responses must not expose internal diagnostics.
5. Promote the matching static frontend artifact after the API is ready. Use the
   guarded clean-directory hosted build; inspect public assets for credentials.
6. Check OAuth origin/callback, CORS, registration retries, waitlist position,
   private media and accessible recovery feedback. Observe maintenance success,
   backlog, connection use and limiter behavior, including after a cold start.

## Application rollback

Keep a reviewed compatible API/frontend artifact pair and a deployment manifest
with exact source revision and checksums. Rehearse it against the migrated schema
before promotion. An older application's strict readiness check may reject a
newer migration head: an arbitrary old image is not a safe rollback artifact.

Pause promotion on a failed smoke check. Return the application artifacts to the
verified compatible pair; preserve the migrated history tables. Do not downgrade
populated history or restore over a live application database. Check readiness,
core reads and authorization again, then resume writes only after review.

For data recovery, restore into a fresh isolated target, authenticate database
and object bytes, replay the separate current erasure ledger through the final
quiesced cutoff, and verify integrity before any manual cutover. Keep interrupted
targets isolated and retain their journals. See [Sprint 28](Sprint-28.md).

## Evidence and unresolved gates

Record revision, CI run, migration head, artifact checksums, dataset, timing,
commands, pass/fail counts and rollback/recovery results in the release ledger.
Provider configuration, scheduler operation, hosted promotion/cutover and human
validation require their own evidence. Local rehearsal is not proof that those
operations have already happened. Keep recurring infrastructure spending at $0;
do not enable automatic paid upgrades.

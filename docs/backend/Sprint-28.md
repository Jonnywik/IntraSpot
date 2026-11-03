# Sprint 28: recovery, retention and account erasure

This checkpoint supplies local developer tooling. Hosted credentials, the private
backup destination and a reliable weekly scheduler must be configured before a
release. There is no automatic public deployment or paid service upgrade.

## Backup operations

Keep database exports and Storage object bytes together with encrypted manifests
and checksums. A database-only success is not a successful recovery point. Use a
32-byte backup key from a protected environment or external owner-only key file.
Keep it in a password manager or equivalent separate location; never commit it,
put it beside the archive, or add it to frontend configuration.

The backup tool uses the application public schema, immutable media objects and
durable backup references. Pending or failed snapshots keep their references
until explicitly retired. Keep four weekly points; make an additional point
before migrations. Premigration points require explicit retirement. Retirement
must remove the archive before releasing its media references.

Configure a weekly operator job on a machine that can reach both the database
and a private destination outside Supabase. Run a catch-up on startup and alert
when the most recent complete pair is over seven days old. A sleeping or powered
off laptop cannot establish the recovery target; scheduling and key custody are
external release gates. No scheduler or provider credential is assumed configured.

## Restore rehearsal

Use `python -m app.backup create --output-root <private-external-folder>` for a
weekly point; add `--purpose premigration` before a migration. Authenticate a
point with `python -m app.backup verify --bundle <snapshot-folder>`. Export the
fresh tombstones with `python -m app.backup export-ledger --output-file
<private-external-ledger>`. The protected backup key must be available for each
operation. `snapshots` lists retained points; `retire --snapshot-id <id>
--output-root <folder>` previews retirement and requires `--apply` to act.

For restoration, set `INTRASPOT_RESTORE_DATABASE_URL` through the operator's
protected environment, then run `python -m app.backup restore --bundle <folder>
--erasure-ledger <fresh-ledger> --erasure-cutoff-at <UTC-ISO-timestamp>
--confirm-erasure-quiescence --target-media-root <new-private-folder>`.
Keep database credentials out of shell history and process arguments. Confirming
quiescence is an operator assertion: the tool cannot prove that all writers or
external jobs have stopped. Preserve the separate current ledger off-provider;
losing it prevents proving that a restored backup will respect later erasures.

1. Quiesce writes and erasure fulfilment before the final current-erasure export.
2. Verify the full encrypted archive and all authentication tags before executing
   SQL or installing media. Retain the current erasure ledger separately from
   the restored backup: the backup cannot know later completed erasures.
3. Restore only into a fresh disposable `intraspot_restore_*` database on loopback
   port 5433, with a separate new media directory. Existing application databases
   and populated targets are rejected.
4. Replay the current erasures before considering the restored target usable.
5. Verify database invariants and every archived media checksum. Record elapsed
   time, snapshot age and failed/interrupted stages. Preserve a failed journal;
   never promote a partial restore.

The internal targets are at most seven days of loss and recovery within one
business day. Rehearse before release and quarterly afterwards; measured local
fixture results do not establish hosted availability or a service-level promise.

## Media and content retention

`python -m app.media_reconcile` produces a bounded dry-run manifest. Use
`--record-observations` for weekly observations and `--apply-manifest <path>`
only after inspecting the saved manifest. Apply rechecks attachments, report and
backup references, age and consecutive findings. Provider uncertainty retains
the object and its quota charge. Detachment alone does not free storage quota.

Announcement retention preserves minimal action metadata while removing old
superseded or removed text after 30 days, subject to existing report evidence
deadlines. Cleanup runs in bounded maintenance transactions. Existing chat and
report windows retain their established rules.

## Erasure operations

Signed-in users request erasure in Settings and receive an opaque receipt with
a 30-calendar-day completion target. The browser cannot fulfil the request.
The explicit operator command is `python -m app.account_erasure fulfill <receipt>`.
Hosted provider deletion requires the additional explicit `--provider-action`.

Transfer organization ownership first. Replace the last active platform
administrator first. There is no silent ownership override. Fulfilment revokes
application access, removes private account data and uses pre-start withdrawal
rules for participation. Organization and event history keeps only necessary
non-login references; bounded report evidence remains until its deadline.
Provider failure leaves the request visibly incomplete and repeatable.

Completed receipts keep dates, outcome and counts for one year. Non-login
tombstones support replay after recovery. Never test erasure on a real local
development account; use only the disposable fictional test database.

# Sprint 28 acceptance — 2026-11-03

Scope: encrypted paired database/object recovery, protected media reconciliation,
30-day announcement retention and operator-mediated account erasure. Main chat
integrated the work; GPT-6 Luna/max workers implemented bounded slices and an
independent reviewer checked privacy/recovery failure scenarios.

## Evidence

| Check | Result |
| --- | --- |
| Focused erasure/retention/interfaces/review/maintenance/recovery | 57 passed, 1 opt-in restore skipped; 77.64 s |
| Actual encrypted PostgreSQL + local object restore and skipped-lock regression | 2 passed; 12.36 s |
| Frontend through Sprint 28 | 171 passed |
| Hosted static export | Passed, clean staging source and synthetic public configuration only |
| Type checking and lint | Passed through the reviewed frontend build/lint commands |
| Additive migration/metadata drift | `alembic check`: no new upgrade operations; head `mvp_0020` |
| Backend locked dependency advisory check | 38 packages, no known OSV advisories at check time |
| Frontend runtime dependency audit | No vulnerabilities; high-severity audit gate passed |
| Existing fictional development dataset | 41 original-table/column aggregates, 76 rows preserved |
| Existing real-development dataset | 41 original-table/column aggregates, 2 rows preserved |
| Delivery credential/build exclusion | Passed |

The local restore used only `intraspot_mvp_test`, a fresh uniquely named
`intraspot_restore_s28_*` target and private temporary object folders. It compared
restored organization/event data and object bytes/hashes, then verified that an
erasure completed after the backup was replayed. The disposable target was
removed after verification. No local development account was erased or imported.

This small fixture restored within the one-business-day target, with a recovery
point created in the same rehearsal. It does not demonstrate a weekly hosted
backup schedule, seven-day hosted recovery-point availability or hosted recovery
time at realistic volume.

## Defects found and corrected

- Cleanup retains reports and active backup references, rechecks holds after
  locking parents, and skips content whose parent could not be locked.
- Erasure cannot be undone by an in-flight profile update or stale organization
  creator. Both paths refresh and lock the authoritative user before writing.
- Event report snapshots retain immutable banner IDs within their size limit;
  reads use the existing report-review scope and evidence deadline.
- Restore authenticates ciphertext before SQL, rejects populated/non-isolated
  targets and requires a fresh erasure ledger through an explicit quiesced
  cutoff. Docker fallback no longer assumes PGPORT is set and keeps psql's input
  stream open. PostgreSQL's built-in schemas are allowed in an empty target.
- A 30-day erasure target is a deadline, rather than a mandatory waiting period.
  Ownership/last-admin blockers remain explicit. Repeated fulfillment/replay and
  bounded cleanup retain their idempotent behavior.

The full PostgreSQL regression executed 848 cases: 830 passed, 13 opt-in browser/
restore checks skipped and five failed (1286.82 s). Two assertions still expected
the old banner-free evidence shape; one expected a projected rather than durable
dry-run observation count; a missing-but-protected media diagnostic had lost its
specific label; and an erasure fixture changed two unique owner roles in an
unsafe flush order. These were corrected without weakening the domain rules.

The affected-domain rerun then passed 219 cases with one opt-in restore skipped
(241.91 s), leaving only the old reconciliation fixture's nonexistent organization
to correct. The final focused rerun records that correction separately. The
independent review's detached-evidence permission tests and stale-profile test
are included in this affected-domain run. Failed runs are not labelled passes;
clean-checkout GitHub CI is checked separately after push. The last reconciliation
fixture rerun passed (1 case, 2.32 s), using a real fictional organization so the
new parent-lock safety check can record observations.

## Remaining release gates

Private off-provider destination, key custody, weekly scheduling/alerts, separate
current erasure-ledger preservation, actual hosted credentials/roles/Storage and
hosted restore/cutover require configuration and evidence. Operator quiescence
confirmation cannot prove that every external writer is stopped. Participant,
physical Android/iOS, NVDA/VoiceOver and positive PLM verification remain pending;
positive PLM testing stays deferred. No paid upgrade, public deployment or release
approval occurred. Development tooling retains moderate transitive npm
advisories; runtime audit is clean and the high-severity gate passes.

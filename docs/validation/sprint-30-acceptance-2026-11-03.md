# Sprint 30 release ledger — 2026-11-03

Candidate base: d7590a3e1ae342b3d62b02fff358116351e5b401. Runtime changes are
the bounded limiter connection queue and pre-dispatch pressure gate in
app/rate_limits.py and app/main.py. Exact tested source/artifact hashes and
rollback revision are in [artifact evidence](sprint30-artifact-results.json).

| Gate | Result |
| --- | --- |
| Clean-checkout integrated baseline | Sprint 29 GitHub backend/frontend success, run 41589905692 |
| Final load, migration, FIFO, worker recovery, rate-limit and saturation tests | 19 passed, 71.11 s |
| Actual packaged S28 → candidate → S28 rollback | Passed, 194.12 s; three readiness/guest-browser/privacy checks, persistent registration and unchanged retries |
| Database budget | 25 shared-IP polling sessions on 3+2 pool; measured ceiling five |
| Registration contention | Ten attempts for three seats; no overbooking; durable ordering, retry replay and one promotion notification |
| Independent Luna/max review | Two dispatch-pressure findings corrected; follow-up source review cleared changes |
| Original local datasets | 41 original-table aggregates preserved: 76 fictional rows and two real-development rows |
| Sprint 28 recovery | Paired encrypted database/object restore and post-backup erasure replay passed; linked Sprint 28 record |
| Sprint 29 frontend/accessibility | 178 frontend checks and 93 rendered checks passed; linked Sprint 29 record |
| Sprint 30 clean-checkout CI | Pending push/run result; do not infer success from baseline |

The release rehearsal built two static exports and packaged API sources without
copying local credential files. Both versions used reviewed mvp_0020 metadata;
no populated-history downgrade occurred. Guest reads exposed no private profile
markers, and each phase retained one registration and one receipt. Earlier
harness runs omitted migration packaging or used an unavailable browser-driver
path; those failures were corrected and the complete rehearsal rerun. Failed
runs are not passes. No hosted promotion or public deployment was performed.

The load check found pool-checkout failures from simultaneous limiter work.
Standalone transactions now queue before checkout; dispatch is capped at 32
active/waiting checks, excess returns 503, and health/readiness/preflight bypass
that dispatch. Cancellation retains a slot until the admitted check completes.
Limits still use shared PostgreSQL state and fail closed on outages.

## External and deferred release dependencies

- Actual participant, physical Android/iOS and NVDA/VoiceOver validation: pending.
- Positive live PLM verification: deferred by user; synthetic tests do not satisfy it.
- Hosted credentials, TLS/roles/Data API/private Storage checks and deployment: not performed here.
- Weekly off-provider backup scheduling, key custody, alerts and hosted-scale restore: require configuration/evidence.
- General-public release and paid upgrades: not authorized. Development-tool moderate npm advisories remain documented; runtime audit and high-severity gate passed in Sprint 28.

Use [the runbook](../backend/Release-runbook.md) before any controlled evaluation.
Local developer verification does not establish release readiness. A commit/push
is not deployment or release approval.

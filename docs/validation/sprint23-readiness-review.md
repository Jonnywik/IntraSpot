# Sprint 23 integrated verification and handoff readiness review

**Review date:** 2026-10-24

**Assessor:** GPT-6 Luna/max subagent, read-only source review.

**Status:** The coordinator has wired the identified timer gap; execution proof is pending. This document is not Sprint 23 acceptance or release approval.

**Coordinator closure:** The historical assessment below is retained. The new
explicit-runner PostgreSQL regression now passes, including exact-boundary
evidence erasure and duplicate-free expiry audit/notice on a second pass. Final
evidence: 688 distinct default cases across serial runs (10 browser skips),
50 synthetic-auth and 147 frontend cases; both exports, dependency audit with
zero known vulnerabilities, focused live browser checks and both complete
development-data hash comparisons pass. Next/eslint-config 16.4.1 and locked
Zod 4.6.7 close the recorded dependency-build gate. See the
[integrated acceptance record](sprint-23-acceptance-2026-10-24.md) for exact
coverage, initial failures and remaining external gates. These are coordinator
executions, not tests performed by the read-only assessor.

## Scope and evidence boundary

Reviewed the canonical Obsidian AI Index, Implementation Roadmap, Security & Operations and Open Questions; repository backend contracts, Sprint 22 contract and acceptance record; and only the implementation seams for profile isolation, timed catch-up, migrations, logging and media access. Graphify was used read-only as navigation.

No tests, database commands, builds, browser actions, dependency edits, migrations, or Git edits were performed by this assessor. Coordinator status below was reported by the orchestrator during review and is historical pending status. Current execution evidence belongs in the integrated acceptance record. Model review is not participant evidence.

## Actionable finding

### P1 — The explicit deadline runner omits Sprint 22 event-safety expiry work

The frozen Sprint 22 contract says an event-report deadline closes the report and erases its evidence snapshot (docs/backend/Sprint-22.md:20-22). The existing sweeper performs that transition: it selects due open/escalated reports, marks them expired, clears evidence, and records an expiry audit (Code/Backend/app/domains/eventsafety/service.py:424-509).

The explicit worker does not call that sweeper. Its run_once path processes registration and moderation deadlines, chat cleanup, invitations, and announcement reports, then exits (Code/Backend/app/deadlines.py:12-43). The report sweeper is only called from event-safety service paths (search found no worker call). Therefore a quiet installation can retain report evidence in the database past its deadline until a relevant event-safety request arrives. The receipt projection hides expired evidence after the deadline, but that does not erase the stored snapshot (Code/Backend/app/domains/eventsafety/service.py:278-285).

The same worker omission delays sealing the expiry audit and sending the expiry notice for quiet organization suspensions. The policy itself stops treating an organization as suspended at the exact boundary using suspended_until > now; this finding is about delayed durable audit/notice, not a claim that restrictions remain active after expiry (Code/Backend/app/core/event_safety.py:17-21; Code/Backend/app/domains/eventsafety/service.py:365-421).

Existing tests prove direct calls to the sweepers, not that the explicit worker catches up these Sprint 22 deadlines (Code/Backend/tests/eventsafety/test_eventsafety.py:669-697). Before declaring integrated handoff complete, wire the existing bounded expiry sweeps into the explicit worker with the existing lock order and add worker-level regression coverage for report evidence deletion and one-time suspension audit/notice. This requires no schema migration.

## Gate and handoff assessment

| Area | Evidence and current boundary |
|---|---|
| Fictional/real isolation | Source configuration rejects mixed auth/database profiles and uses separate fictional and real-development database names plus separate media subdirectories (Code/Backend/app/core/config.py:28-58). Sprint 22 acceptance records preserved all 37 prior tables, with 76 fictional and 2 real-development rows, in separate databases (docs/validation/sprint-22-acceptance-2026-10-24.md:49-54). Coordinator reports both current 41-table hash baselines captured; the final comparison is pending. No credentials or local environment files were inspected. |
| Migrations and recovery | Sprint 22 used explicit additive mvp_0017; startup migration is absent and downgrade refuses nonempty safety tables (docs/validation/sprint-22-acceptance-2026-10-24.md:49-54). Coordinator reports no migration is planned for Sprint 23. The canonical recovery decision keeps restoration untested until a real data-loss incident, so restoration readiness is not verified (Security & Operations, “Retention and recovery”). Back up SQL and its media partition together. |
| Timed work | The worker is an explicit local process, not an API-startup timer (Code/Backend/app/deadlines.py:1, 46-58). Sprint 22 report evidence expiry is due at its contract deadline; the missing worker integration is the finding above. Production scheduling/deployment remains outside this authorization. |
| Logs and media privacy | Request logs contain request ID, route/action and status, with no request body or identity fields (Code/Backend/app/main.py:37-49). Media reads authorize current attachment/visibility before returning bytes (Code/Backend/app/domains/media/service.py:190-228), and profile storage roots are separated (config.py:54-58). Replaced or rolled-back media files remain inaccessible but retained; reconciliation and quotas remain pre-hosting work (Security & Operations, “Current local-media/auth checkpoint”). |
| Developer versus release claims | Sprint 22 is local implementation evidence only. Its acceptance record leaves browser, participant, physical-device/accessibility, live PLM-account, operational-security and release approval open (docs/validation/sprint-22-acceptance-2026-10-24.md:87-100). The actual-app browser question is pending; no browser result is claimed here. |
| Test coverage | Sprint 22 recorded 359 distinct PostgreSQL cases across serial runs, 50 synthetic-auth cases and 140 frontend checks, explicitly not a full repository rerun (acceptance:68-74). The coordinator reported a full run after duplicate attendance/registration module basenames caused initial collection failure and import mode changed to importlib. The number 20201 identified the command session, not a test count. This assessor ran no tests. |
| Dependency gate | Coordinator reports the three Next advisories were addressed by pinning Next and eslint-config to 16.4.1 and completing installation. A development Zod 4.6.5 advisory is still being addressed. The audited dependency result is pending and was not independently checked here. |
| Handoff notes | Coordinator identified docs/backend/README as stale at Sprint 21 and plans to update it to Sprint 23. This assessor did not edit it. |

## Completion boundary

Close the local handoff only after the worker expiry gap is addressed and the coordinator’s full-suite, dependency audit, and data-hash comparison results are recorded. Keep the requested real-app browser check pending until the user opens the actual app. Participant validation, live PLM sign-in, deployment, backup restoration rehearsal, and release approval remain separate gates; none is implied by this review.

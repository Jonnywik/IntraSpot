# Sprint 23 — integrated developer verification and handoff

Date: 2026-10-24. **Local developer checkpoint complete; not release approval.**
The coordinator owns execution; model reviews are supporting source evidence.

## Verified changes

- Pin Next.js and eslint-config-next to 16.4.1 and update the compatible locked
  development Zod dependency to 4.6.7. No major-version migration, audit suppression
  or unreviewed automatic upgrade. Next's image dependency resolves sharp 0.35.5.
- Configure pytest importlib mode so attendance and registration test filenames
  can be collected together. Preserve all cases; update the old bounded-query
  expectation for the batched safety lookup and forward current visibility
  arguments through the social clock-boundary test adapter.
- Suspension takes organization then sorted published-event locks, sharing the
  admission writer's serialization boundary. An in-flight decision must finish
  before suspension commits; later new joins fail. Existing reviews/FIFO/chat
  behavior remains 2A. A direct hide cannot contradict a draft's `can_hide: false`.
- The explicit deadline runner also processes event-report evidence expiry and
  suspension expiry audit/notices, including quiet installations after downtime.
  No migrations or background timer are added to API startup.
- Review UI names the target of an uncertain retry and gives accurate conflict
  guidance. Applied success requires the matching report ID, next version and
  requested action/status. An HTTP 200 expiry sweep is shown as expired, without
  claiming the requested decision was applied. Original retries stay in memory.
- Add the [local developer handoff](../backend/local-handoff.md) and update the
  repository entrypoint. Keep canonical Obsidian notes authoritative.

## Dependency evidence

The registry audit identified three Next advisories affecting the installed
16.4.0. Maintainer-reviewed advisories list 16.4.1 as patched:
[image optimization](https://github.com/advisories/GHSA-2464-fhr4-w9xw),
[Server Actions denial of service](https://github.com/advisories/GHSA-p3m5-59mp-jv5r),
and [typed-array cache handling](https://github.com/advisories/GHSA-673q-mjm6-r5xr).
The development-only Zod advisory affects versions below 4.6.6; the compatible
lockfile update resolves 4.6.7. See the [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5).
Current npm audit reports zero known vulnerabilities, including development
dependencies. This is a registry check at this date, not a universal security
certification or proof that this static local app exposed each affected feature.

## Actual verification ledger

| Check | Result |
|---|---|
| Default PostgreSQL coverage | **688 distinct cases passed across serial runs; 10 opt-in browser cases skipped; no unresolved failures**. Full sweep and corrections detailed below |
| New suspension/admission race and draft-hide regression | Passed against real PostgreSQL, including observed lock blocking, denied later join, preserved FIFO promotion and original receipt replay |
| Explicit runner quiet-expiry regression | Passed: exact-boundary evidence deletion and suspension expiry; second pass creates no duplicate audit or notice |
| Synthetic Supabase protocol suite | **50 passed** against its separate scratch database; not live Google/PLM sign-in |
| Complete frontend Node suite including Sprint 23 | **147 passed** |
| Whole frontend ESLint and TypeScript | Passed |
| Final fictional frontend export | Passed; all 14 generated pages plus public/static credential guard |
| Final separate real-auth export | Passed; all 14 generated pages plus public/static credential guard |
| npm audit including development dependencies | **0 known vulnerabilities** |
| Alembic drift / saved OpenAPI equality | Passed, unchanged `mvp_0017`; no schema change |
| Fictional live HTTP | Twelve app routes return 200; API ready, four existing public events; private guest request denied; both allowed PUT preflights pass and external origin fails |
| Real-development live HTTP | Frontend/API ready; fictional catalog 404, guest profile 401, real origin allowed, fictional origin rejected |
| Actual fictional API restart | New process instance, same ready schema/public response hash; read-only, no registration/fixture mutation |
| Existing data preservation | Final hashes match the before snapshot for all **41 tables**, separately: **76 fictional-development rows, 2 real-development rows** |
| Focused live browser | Actual app guest discovery/detail, eligible faculty registration/report dialog dismissal and focus return, owner safety controls, platform admin empty report queue and guest restoration verified; no data-changing actions submitted |

The full database suites target only the named scratch databases and execute
serially. The complete default sweep finished with **678 passed, 7 failed and
10 skipped** in 3258.80 seconds. Four request/process-start timeout failures then
passed in isolation (**4 passed**, 75.33 seconds), without increasing timeouts.
Concurrent frontend build load occurred during the sweep, but is not established
as the sole cause. Three stale test expectations/adapters were corrected as above.
The final affected run passed **33 cases**, including those three, all event-safety
domain cases, Sprint 22 quality cases and three new Sprint 23 backend cases
(102.80 seconds). Final authentication run: **50 passed** (23.85 seconds).

JUnit evidence is retained locally in ignored `Code/Backend/.cache/`:
`s23-full-final.xml`, `s23-timeouts.xml`, `s23-focused.xml` and `s23-auth.xml`.
De-duplicating default cases by class/name and using the last result gives
688 passing cases, 10 skips and zero unresolved failures. This is not represented
as a single clean full-suite rerun. The long sweep was not repeated after the
focused fixes; changed production paths and corrected tests received affected
reruns. Starlette/httpx deprecation warnings remain non-failing maintenance work.

### Browser evidence and limits

The initial internal connection-error page became inspectable after both local
servers were started and the user refreshed the actual app. No policy bypass or
alternate-browser workaround was used. The check used the existing in-app browser
at **790 CSS pixels**, not the full target viewport/device matrix.

- A guest opened public event details with separate interest, confirmed, reserved
  and remaining-seat counts, plus sign-in guidance.
- The fictional faculty account could open registration and report confirmations.
  Escape dismissed each and returned DOM/accessibility focus to its trigger.
  Report confirmation initially focused Cancel. Detail had no horizontal overflow.
- The approved organization owner saw its scoped Hide and Cancel controls, with
  separate organization/platform hide status and the existing-participation copy.
  The platform administrator opened its safety queue and received a usable empty
  state. No hide, cancel, report, registration, reaction or save was submitted.
- Guest mode and Discover were restored. Final database hashes still matched.
  Expired fixture catalog tokens were renewed locally using the existing fixed
  catalog operation; signing keys were not rotated and database rows did not change.

Screenshots: [faculty event details](sprint23-browser-evidence/faculty-event.png)
and [report confirmation](sprint23-browser-evidence/report-confirmation.png).
These focused checks do not execute the ten skipped historical browser tests or
establish a participant, complete responsive, physical-device or accessibility pass.

## Review records

Three non-overlapping GPT-6 Luna/max workers reviewed backend safety, UI behavior
and readiness. The coordinator owned test configuration, deadline-runner wiring,
dependency locks, serial execution, operational checks and handoff/delivery.
See [safety review](sprint23-safety-review.md), [UI review](sprint23-ui-review.md)
and [readiness review](sprint23-readiness-review.md). Review notes distinguish
the worker's static/focused checks from the coordinator's integrated executions.

## Open boundaries

No participant test, live PLM-account sign-in, full native-device/accessibility
matrix, deployment, Penpot synchronization or cloud application-data migration is
claimed. Focused browser evidence above closes only those observed checks;
historical opt-in browser gates are not silently enabled or counted as passed.

Long-term retention/deletion, local media reconciliation/quotas and hosting
operations remain their recorded future decisions. The accepted pilot recovery
decision does not rehearse restores before an incident, so backup restoration
readiness remains unverified. No database reset, broad seed, volume deletion or
Penpot database operation was performed. Checkpoints are pushed per standing
instruction after verification; a GitHub push is not launch approval.

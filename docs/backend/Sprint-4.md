# Sprint 4 — capacity-safe registration and waitlists

Authorized by the user's next-sprint request on 2026-10-13. The preceding
repair pass verified registration seams but did not accept this full milestone.

## Acceptance and boundaries

- Eligible, profile-complete fictional students and faculty can register for
  published, future instant-registration events.
- Durable per-event receipt order determines capacity decisions. A client key
  is mandatory; replay returns the stored original outcome, not today's state.
- Different keys cannot create duplicate active registrations. Incompatible
  reuse across events conflicts without consuming another event's admission.
- Pre-start withdrawal promotes the earliest waiter and records one durable
  in-app notification in the same transaction. Repeated withdrawals are safe.
- Immediate outcomes and My Events expose waitlist position and no estimated
  wait time. My Events and notifications expose only the signed-in user's rows.
- PostgreSQL concurrency and independent-process restart proof are required.

No frontend integration, approval registrations, chat, cloud auth, deployment,
Penpot edits, database resets outside the isolated test database, or real users.

## Parallel ownership

The main chat coordinates and owns production fixes, shared infrastructure,
notifications, contracts and final serial verification. Four GPT-6 Luna/max
workers own distinct new test files:

| Worker | Exclusive file and acceptance angle |
|---|---|
| API | `tests/registrations/test_sprint4_api.py`: access and response boundaries |
| Recovery | `tests/registrations/test_sprint4_recovery.py`: subprocess recovery |
| Races | `tests/registrations/test_sprint4_races.py`: competing capacity mutations |
| Quality assessor | `tests/quality/test_sprint4_acceptance.py`: transaction fault review |

Workers report production issues to the coordinator. They do not run pytest
concurrently: the shared fixtures truncate the same guarded scratch database.
The tool does not expose a separate fast-mode control; none is claimed.

## Verification

Run the full backend suite serially against `intraspot_mvp_test` on loopback
5433, followed by migration drift and OpenAPI freshness checks. The shared
`test_sprint4_http.py` starts its own loopback API processes, demonstrates ten
requests competing for three seats, withdrawal/promotion, privacy and replay,
then stops and restarts the API to verify persisted results and notifications.

Record measured results and any remaining limitations in the acceptance report.
Participant validation and security/release checks still gate real-user release.

## Completed checkpoint

The final combined gate passed **173 checks** in 103.22 seconds, with one
dependency deprecation warning. Migration drift and saved OpenAPI freshness
checks passed. See [acceptance and next-sprint handoff](../validation/sprint-4-acceptance-2026-10-13.md).
All four workers are closed. Sprint 5 is next, not implemented by this sprint.

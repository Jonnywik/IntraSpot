# Sprint 3 acceptance — events and public discovery

**Local backend milestone passed — 2026-10-13.** Stop at Sprint 3. Sprint 4 capacity/waitlist acceptance, Sprint 5 frontend integration and real-user release remain deferred.

## Scope and authority

The user's approved MVP plan and explicit request to proceed authorize fictional local implementation only. Canonical Obsidian product, privacy and unresolved-decision notes were verified through Graphify and the AI Index. The canonical prototype-only stage wording remains a participant/release gate; it is not a prohibition on the explicitly authorized isolated local backend work. No canonical note, Penpot file, mobile design, frontend or cloud service was modified in this sprint.

The main chat coordinated five GPT-6 Luna/max workers with disjoint draft/publish, discovery, lifecycle, fixture and quality scopes. No Sol coordinator subagent was used. Fast-mode selection is not exposed by the agent tool and is not claimed. All five agents are closed. The coordinator independently ran the tests and live checks; worker syntax checks were not substituted for acceptance.

## Completed behavior

- Active eligible organization owners/admins save incomplete drafts and access private previews. Pending organizations may draft but cannot publish; rejected organizations remain read-only. Approved organizations may publish complete valid events.
- Scheduled/instant publishing requires title, description, venue name/address, future aware start, later end, positive capacity and an allowed fixture-artwork key. Summary remains optional and defaults to an empty string; cost is informational. Capacity input fits PostgreSQL Integer storage, and time comparisons use UTC instants.
- Public discovery/detail expose no creator, registrant or private profile data and never expose drafts. Historical published details remain readable.
- Literal case-insensitive search matches event titles and organization names, not venues. Search composes with My Clubs and Upcoming/Newest sorting. Start/publication sorting uses stable ascending ID tie-breakers. Eligible users without active memberships receive an empty My Clubs result; guests retain global browsing/search without that filter.
- Confirmed attendance, remaining capacity and interest counts are independent values. Ongoing events remain discoverable; ended events are excluded, including the exact end boundary. Registration is denied at and after start.
- Published material edits and organizer cancellation remain unavailable. No approval-mode registration, membership-management, social/chat/media-upload or payment workflow was added.

## Implemented fixes and review findings

1. Bound API capacity by the existing signed 32-bit PostgreSQL column, avoiding a storage error for otherwise positive oversized inputs.
2. Compare event times as UTC instants, avoiding repeated-hour timezone ordering errors.
3. The additive local fixture command rechecks pending accreditation under the same refreshed organization lock as draft creation, including concurrent rejection.
4. The independent quality assessor found a private-draft lifecycle defect. The coordinator reproduced it: a durable request made against a draft could become confirmed when processed after publication. Intake now rejects drafts without allocating an order/receipt; publication terminalizes legacy unfinished draft attempts as rejected in the same transaction, before public reads can drain them. Retry results remain rejected, and failed publication rolls back both changes. This narrow privacy repair touches the pre-existing registration seam but does not accept or expand Sprint 4. No schema change or timestamp inference was used.

## Independent verification

| Gate | Result |
|---|---|
| Prior-sprint regressions | 70 passed |
| Focused discovery | 3 passed |
| Focused drafts/publishing | 14 passed |
| Focused local fixtures | 18 passed |
| Focused lifecycle | 4 passed |
| Focused quality/privacy after fix | 3 passed |
| Combined final Sprint 1–3 gate | **127 passed, 2 warnings, 43.41 s** |
| Live loopback HTTP and distinct-instance restart | **10 check groups passed** |
| Reviewed schema drift | `alembic check`: no new upgrade operations; head remains `mvp_0001` |
| OpenAPI | Regenerated and reviewed; capacity maximum 2147483647, no new route or migration |

Combined command, from `Code/Backend`:

```powershell
rtk proxy .mvp-venv/Scripts/python.exe -m pytest -q tests/identity tests/organizations tests/events tests/shared/test_foundation.py tests/shared/test_local_identities.py tests/shared/test_local_organizations.py tests/shared/test_local_events.py tests/quality --maxfail=1
```

All tests ran serially against real PostgreSQL 17 on loopback port 5433. Per-test resets asserted `intraspot_mvp_test`; development data was not truncated. The two observed warnings were the existing TestClient/httpx deprecation and a Pydantic field-metadata warning during the concurrent-publication test. Passing route/validation and OpenAPI checks are recorded without claiming those dependency warnings have been eliminated.

The live harness is [sprint3-api-check.mjs](sprint3-api-check.mjs); results are [sprint3-live-results.json](sprint3-live-results.json). Its before/after stages checked different API instance IDs and preserved public event fields/counts and private drafts. The final source also denied oversized capacity and draft registration without mutation. It uses only predefined fictional accounts and additive sample records; no token, email, profile or request-body logging was added. Ignored signing keys, account tokens, local environment and restart snapshots were confirmed excluded from Git tracking.

## Runtime and data preservation

Docker's stale runtime sockets recurred. Only two validated zero-byte socket directories were moved to recoverable backups; containers/volumes were not deleted. See [Docker recovery](docker-repair-2026-10-13.md). Existing Penpot containers were not reconfigured and Penpot's PostgreSQL database was not accessed or migrated.

`app.local_events` adds one fixed incomplete pending draft and two fixed approved public events. The live demonstration also retains its clearly fictional organization/drafts/events for restart evidence. A second fixture run preserved all 13 development event rows and their complete state digest; final rejected HTTP checks preserved the same digest. Existing timestamps, lifecycle, draft edits, privileges, memberships and accreditation decisions were not reset. The fixture command accepts no arbitrary identity, organization or database arguments and refuses non-local/non-development targets.

The final local API runs at `http://127.0.0.1:8001` with access logging disabled. It remains fictional/local-only. No dependency, database model or migration was changed.

## Remaining gates

- Sprint 4 still needs its full capacity, concurrent admission/order, retries, withdrawal/promotion, notification and restart-recovery acceptance. This sprint's privacy/start-boundary tests are not a substitute.
- Sprint 5 still needs API-driven frontend journeys and generated frontend types; the current frontend is not accepted as integrated.
- Participant validation and security/release checks remain mandatory before real users. No deployment, real OAuth, Supabase connection or production-readiness claim is made.
- Docker is working now; this recovery does not prove the Windows socket issue cannot recur.

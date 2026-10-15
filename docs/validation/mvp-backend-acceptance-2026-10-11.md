# Local MVP implementation acceptance

Date: 2026-10-11 (Asia/Manila). This document records independent acceptance checks for the user-authorized local five-sprint MVP. It does not replace canonical Obsidian product notes or certify participant testing.

**Scope override:** The user subsequently requested stopping after Sprint 1. Later-sprint files already saved are preserved, but are preliminary and not accepted as completed. Frontend integration and later journeys are paused. The matrix below retains the original full-MVP targets for future work; only the Sprint 1 gate is being completed now.

## Authorization and boundaries

- Four GPT-6 Luna/max domain workers; GPT-6.1 Sol/high coordinates contracts, migrations and integration. Agent tools do not expose a fixed 1.5× speed setting.
- Only fictional local identities and a dedicated PostgreSQL 17 instance. Penpot and its PostgreSQL service must remain unchanged.
- Local implementation may advance while participant validation remains open; real-user release, real Google OAuth and cloud services remain blocked.
- Instant registration and waitlists only. Complex approvals, material-change reconfirmation, social/chat/reporting, membership intake and succession remain deferred.
- User selected PLM root and dot-delimited subdomains as eligibility policy. Browser-provided identity, email/role edits and client timestamps cannot establish authorization or ordering.

## Acceptance matrix

| Area | Required independent check | Evidence status |
| --- | --- | --- |
| Local infrastructure | Dedicated loopback PostgreSQL 17; explicit reviewed Alembic upgrades; no automatic startup migrations; existing Penpot services untouched | Sprint 1 passed: container inventory, migration/current drift check, focused tests and live readiness |
| Authentication | Signed local fixture accepted only in local/test; forged/expired/wrong-issuer/wrong-audience/wrong-subject tokens denied; fixture mode rejected outside local/test | Sprint 1 passed: focused tests and live protected endpoints |
| Eligibility | Trusted student/faculty fixture domains accepted; non-PLM and deceptive suffixes denied; posted eligibility/admin flags cannot escalate | Sprint 1 passed: DB-derived identity tests; live privilege edit denied |
| Profile privacy | Own profile read/update only; nickname, age bracket and tag required for registration; guest and other-user projections contain no private persona/email | Sprint 1 profile validation/privacy passed; registration enforcement deferred to Sprint 4 acceptance |
| Organization permissions | Creator is owner; pending may draft but not publish; unrelated members and moderators cannot author or decide accreditation | Not run |
| Accreditation | Platform admin alone decides; outcome/admin/server time recorded; rejection read-only; no evidence upload or LinkedIn proof | Not run |
| Event discovery | Public published-only list/details; drafts private; title/org search composes with Upcoming/Newest and active-member My Clubs; venue excluded | Not run |
| Public counts | Confirmed attendance and remaining spots separate; no reactions masquerading as attendance | Not run |
| Registration race | Ten valid concurrent attempts for three seats yield exactly three confirmations and seven waitlists on real PostgreSQL | Not run |
| Ordering | Persisted platform admission sequence controls processing and waitlist promotion; client timestamps ignored; database lock acquisition alone is not claimed as arrival FIFO | Not run |
| Idempotency | Concurrent same-key retry and response-loss replay return original outcome; changed payload/key scope conflicts; different key cannot duplicate active registration | Not run |
| Withdrawal/promotion | Pre-start withdrawal promotes earliest waiter once; promotion notification atomic and durable; repeated withdrawal cannot duplicate it | Not run |
| My Events | Only caller's records; immediate waitlist position/no estimated wait time; Past projection after event end | Not run |
| Lifecycle/recovery | Started/ended events reject joins; ended events leave active discovery; restart preserves accepted outcomes and safely resumes admitted work | Not run |
| API errors/logs | Stable machine-readable errors, explicit local CORS, no tokens/emails/profile fields/full bodies in logs or echoed errors | Sprint 1 passed: focused metadata-only logging/CORS/rollback tests and sanitized live errors |
| Frontend integration | Real local API browsing, registration/My Events, owner draft/publish and admin decisions; no static outcomes substituted | Not run |
| Responsive UI | Approved identity, constrained feed, centered controls, mobile four tabs, management desktop-only, loading/empty/error/success/disabled feedback | Not run |
| Build/contracts | Backend tests, frontend build/lint/typecheck, reviewed OpenAPI-generated types | Not run |

## Evidence rules

Record actual commands/results and distinguish API tests, browser interaction tests, screenshot inspection and participant validation. Do not label structural checks as live interaction testing. Mark unavailable tests blocked or not run rather than passing them.

The prototype geometry baseline uses 72 px desktop navigation, a centered workspace capped at 1200 px, a constrained single-column feed around 680 px, warm ivory/white, burgundy identity, navy actions and functional gold. Desktop headings/event titles use Noto Serif Georgian; controls and metadata use Inter Tight. Final UI acceptance needs actual rendered text: some existing Penpot image exports omit font glyphs and cannot prove typography alignment by themselves.

## Final verification results

Sprint 1 final focused backend gate: **34 passed**, one upstream TestClient deprecation warning, in 9.77 seconds. This includes the two new identity-only fixture tests.

Command (from `Code/Backend`): `.mvp-venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider tests/identity tests/shared/test_foundation.py tests/shared/test_local_identities.py`, run through RTK.

This verifies signed-token handling, DB-derived eligibility/privileges, self-profile privacy and validation, local configuration restrictions, isolated database migrations, health/readiness, CORS, metadata-only logging, and rollback before a false success response. The previously failing nonempty grant projection now passes. `alembic current` reports `mvp_0001 (head)` and independent `alembic check` reports no new upgrade operations.

Live API demonstration on `http://127.0.0.1:8001`: **9 HTTP checks passed**. Health/readiness returned 200; guest identity/profile access and forged authentication returned 401; the predefined fictional student could read the DB-derived actor and private profile, save the same profile values successfully, and could not add a platform-admin field (422). Public actor/profile payloads omitted raw email. Credentials and profile contents were not printed.

No frontend/browser journey acceptance or participant testing is claimed. All four domain workers and the coordinator have been stopped and closed. The Sprint 1-only `app.local_identities` generator is complete: it creates fixed fictional users and renews short-lived tokens in ignored `Backend/.local/accounts.json`, without organization/event/frontend writes. It is idempotent, preserves edited profiles, and rejects identity collisions. The 9 live HTTP checks were repeated successfully using this identity-only manifest.

Closing the coordinator ended its temporary API process. A sandboxed restart was unreachable and stopped; a loopback-only local restart outside that restriction succeeded. The latest live checks ran against that process on port 8001. No application code change was needed for this environment limitation.

### Backend gate, first independent run

`Code/Backend/.mvp-venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider`: **62 passed, 2 failed**, against isolated real PostgreSQL, in 37.22 seconds. Domain owners were asked to correct the failures before advancing:

- Current-user serialization with nonempty organization grants returned 500; identity owner is fixing the response projection.
- Event publishing privacy assertion rejected the ordinary word “title” in a sanitized required-fields message; event owner is changing the assertion to check actual private values rather than public field names.

The registration capacity race, durable admission ordering, same-key retry, withdrawal/promotion, single-notification and pending-receipt recovery tests passed in this run. This does not yet prove a live server process restart or browser journeys.

### Independent implementation review

- Container inventory confirms `intraspot-mvp-postgres-1`, image `postgres:17`, bound to `127.0.0.1:5433`. Penpot retains its distinct `postgres:15` service and existing containers.
- Initial migration uses frozen, explicit Alembic table/index/constraint operations; application startup does not execute migrations.
- Auth implementation accepts RS256 only and validates issuer, audience, expiry and UUID subject. Eligibility and platform privileges are derived from database users, not editable profile fields or token metadata.
- Registration intake durably assigns an event admission sequence before draining receipts in that order; registration, original retry result and promotion notification use owned database transactions.
- Review requested regressions for new-key registration after start, invalid published capacity, rejected-organization mutation, and failed commits before a success response. Their test results are still pending.
- FastAPI's [dependency scope documentation](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope) was checked when reviewing commit timing: a function-scoped dependency exits before the response is sent. The regression must prove the implementation, not just rely on this documentation.

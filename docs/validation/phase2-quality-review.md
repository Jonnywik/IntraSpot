# Sprint 2 independent quality review

Review scope: organization/accreditation security and atomicity, event draft/publish integration, fixed local organization fixtures, and the independent live HTTP checker. Review followed the stop gates in `docs/backend/Phase-2.md`; no frontend, cloud, Penpot, broader event lifecycle, or participant-release claims are in scope.

## Confirmed defects fixed

- Concurrent publication could accept the same draft twice. `publish_event` loaded the Event before taking the organization row lock. A second request could wait for the first publisher, then continue using its already-loaded `draft` object after the first request committed. The route now refreshes and row-locks the Event after the organization lock; the later request sees `published` and receives the existing `published_event_immutable` 409. Regression: `test_concurrent_publish_uses_event_state_after_organization_lock`.
- Draft patching had the same stale-object race: it loaded Event before the organization lock, then `update_draft` trusted cached `event.status`. A patch waiting behind publication could therefore overwrite fields after the event became published. The route now refreshes and row-locks Event after the organization lock and policy check. Regression: `test_draft_patch_refreshes_event_after_waiting_for_organization_lock`.
- The stale-organization event test directly called a route function, bypassing `get_db` transaction cleanup. Its denied create left an organization row lock held while the test's second Session attempted to lock that row. The test now asserts the refreshed `rejected` value before rollback, rolls back that Session, and also releases the second Session's denied-patch transaction before subsequent queries. Regression retained in `test_draft_writes_refresh_stale_organization_after_rejection`.
- The initial root serial run exposed a missing `make_event` fixture argument in `test_only_active_owner_or_admin_can_create_and_edit_drafts`; the fixture is now declared by that test.

## Adversarial regression coverage added

- `test_accreditation_endpoint_rechecks_current_admin_identity_for_existing_token` changes platform-admin, verified-email, or active status after token issuance, then verifies the decision endpoint denies access and leaves the pending application without an audit row.
- `test_failed_accreditation_commit_rolls_back_status_and_audit` allows the decision service to flush both the terminal status and audit row, injects a commit failure through the same `get_db` transaction path used by requests, and verifies from a fresh Session that the organization remains pending with no decision.
- Existing organization-worker coverage was reviewed: stale database privilege/email changes are re-read, and independent concurrent accreditation decisions explicitly roll back the losing Session before reporting its conflict. No duplicate broad decision-race test was added here.

## Other reviewed boundaries

- `app/local_organizations.py` uses `session_factory()()` correctly: the first call returns a sessionmaker and the second creates a Session. `ensure_organizations` uses a nested transaction without committing its caller's transaction; the command wraps it in an outer transaction. The shared fixture tests cover additive creation, preservation of edits, collisions, and decision-failure rollback. No additional fixture defect was confirmed.
- `require_platform_admin` reloads the User row with `populate_existing=True` and checks active status, current platform-admin privilege, and current email eligibility. The tests cover changes made before the authorization query; an authorization that was valid when checked but revoked concurrently afterward is treated as an in-flight request race, not reported here as a proven Sprint 2 defect.
- `docs/validation/phase2-api-check.mjs` passed Node's syntax check. Static review confirms it targets loopback local HTTP, uses fixed fictional accounts, and performs additive checks without database resets. It was not executed because it changes local data and the live service/test slot belongs to the coordinator.

## Verification status and stop gate

Static verification completed: Python AST parsing passed for seven owned/reviewed backend files using `Code/Backend/.mvp-venv/Scripts/python.exe`; `node --check` passed for `docs/validation/phase2-api-check.mjs` on Node v26.7.0. The coordinator separately reported root `compileall` and initial/focused collection counts of 64 and 15 as successful; those were compile/collection checks, not test execution.

The first root serial run reported 42 passed and one failed in 60.47s. The failure was `test_only_active_owner_or_admin_can_create_and_edit_drafts`, caused by its missing `make_event` fixture; this worker added the fixture argument. This worker also fixed the stale published-event PATCH race and added its deterministic regression. Root verified these fixes were already present and did not apply a duplicate patch.

This worker's first targeted invocation was interrupted during ownership transfer after emitting two progress dots (session 58391 exited 1), without a pytest summary; those dots do not establish a result. Root reran the exact eight targeted PostgreSQL regression cases listed below: all eight passed in 14.15s, with one upstream TestClient deprecation warning.

Root reports the live HTTP checker passed all eight groups before restart. The full Sprint 1 + Sprint 2 + event-boundary PostgreSQL suite then passed: 85 tests, one upstream TestClient deprecation warning, in 44.70s. The post-restart live HTTP proof also passed against a distinct service instance; workspaces, accreditation audits, and the draft were identical before and after restart. Alembic reported no schema drift. A live fixture rerun left three organizations, 12 grants, and two audit rows unchanged.

The targeted cases are:

- `tests/quality/test_sprint2_quality.py::test_accreditation_endpoint_rechecks_current_admin_identity_for_existing_token`
- `tests/quality/test_sprint2_quality.py::test_failed_accreditation_commit_rolls_back_status_and_audit`
- `tests/events/test_events_api.py::test_draft_writes_refresh_stale_organization_after_rejection`
- `tests/events/test_events_api.py::test_concurrent_publish_uses_event_state_after_organization_lock`
- `tests/events/test_events_api.py::test_draft_patch_refreshes_event_after_waiting_for_organization_lock`

The focused eight-case PostgreSQL run, full 85-test regression suite, pre- and post-restart HTTP checks, no-drift result, and non-mutating fixture rerun are verified by root’s report. The acceptance record is [sprint-2-acceptance-2026-10-12.md](sprint-2-acceptance-2026-10-12.md). Root accepted Sprint 2 only; this review makes no production-deployment or frontend acceptance claim.

# Sprint 21 Independent Quality Review

Coordinator addendum, 2026-10-24: all three HTTP cases passed after aligning the
clarified registration-reference expectation and recovering the stopped database
container. See [integrated evidence](sprint-21-acceptance-2026-10-24.md). The
assessor did not independently execute those checks or certify browser behavior.

## Scope and execution boundary

Read the frozen contract in `docs/backend/Sprint-21.md` in full, then audited the integrated attendance routes, schemas, service, models and migration; API router registration; event status model; registration withdrawal route/service; ownership-transfer behavior; and existing HTTP fixtures/quality-test patterns. The new independent coverage is limited to three HTTP journeys in `Code/Backend/tests/quality/test_sprint21_quality.py`:

1. Staff-role access, non-staff and cross-organization denial, a historical event, confirmed-only roster, safe response fields, the closed check-in gate, and a registration/event mismatch. Owner, admin and moderator each exercise an authorized write.
2. Exact stored-response retry while authorized, incompatible client-key reuse, then loss of access to that same replay after ownership transfer.
3. Registration cancellation after check-in: the mark and audit history remain, but the cancelled registration leaves the current confirmed and checked-in counts; subsequent marking is rejected. The journey also snapshots registration state, event capacity/admission fields and chat-row count around attendance writes.

The first focused run had two passes and one failure, solely because the test expected the superseded `Member · CODE` label. The current frozen contract now explicitly requires `Registration · UUID`; the assertion below has been updated to that exact opaque registration reference. Per your request, rerun only this QA file in the serial PostgreSQL slot; no builds or migrations are in scope. The HTTP expectations are based on the actual routes and service errors, not inferred response codes. Concurrency stress is left to the domain worker's three Postgres concurrency tests rather than duplicated here; the lock sequence was source-audited.

## Contract correction; no production defect

- The prior review's `Member · CODE` expectation is superseded by the clarified frozen contract in `docs/backend/Sprint-21.md`. `Code/Backend/app/domains/attendance/service.py:147` returns the required `Registration · {registration.id}` reference. The test now asserts that exact format and exact response-field sets, and continues to check that attendee email, user ID and profile/nickname fields are absent. This reference is for matching only the same attendee's own confirmed My Events/result, and is not an identity proof. This is not a production defect.

## Confirmed behavior and boundaries

- Attendance reads require an active owner/admin/moderator membership (`service.py:18,32-35`); writes lock/recheck current staff access (`service.py:40-70`). The write flow discovers the organization, serializes the client key, locks the organization membership, locks the event, verifies its organization, and rechecks authority. Stored-result replay follows that authority check and precedes version validation (`service.py:188-210,253-276`). This supports denying a former owner's retry after transfer.
- The roster query selects only `confirmed` registrations and orders by admission order (`service.py:132-152`). Writes reject a closed gate with HTTP 409 / `attendance_checkin_closed` (`service.py:279-287`) and reject a missing, cross-event, or no-longer-confirmed registration with HTTP 409 / `attendance_registration_unavailable` (`service.py:289-303`). The route decorators define no success override, so attendance GET/POST/PUT success is HTTP 200 (`routes.py:24-68`). Staff authorization failures are 403; unauthenticated reads are 401.
- Registration withdrawal is a separate existing endpoint, `DELETE /api/v1/events/{event_id}/registrations/me`, and returns the current cancellation result (HTTP 200 in the existing route contract). Sprint 21 does not define a public event cancellation/removal endpoint: the event model constrains status to `draft` or `published` (`events/models.py:11-15`), and the reviewed attendance routes add no lifecycle endpoint. Event cancellation/removal therefore remains an explicit Sprint 22 dependency; this review does not invent or test such an API.
- Attendance projection counts the event's current confirmed roster, while history is persisted audit rows. Registration cancellation does not delete the mark or audit; the new journey checks the persisted mark and equal parsed history responses while verifying current counts exclude the cancelled registration.

## Not claimed

The HTTP file has not been executed against PostgreSQL, so this review makes no runtime pass claim. The concurrency behavior is assessed from the source lock/recheck sequence and is delegated to the domain worker's separate race tests. No event-cancellation behavior is claimed or fabricated.

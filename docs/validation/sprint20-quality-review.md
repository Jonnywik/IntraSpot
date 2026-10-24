# Sprint 20 independent quality review

**Assessment:** boundary regression coverage prepared; PostgreSQL behavior remains unverified by this assessor. No confirmed backend ownership defect was found in the focused source review.

Coordinator addendum, 2026-10-23: all 14 independent QA cases passed in the final
36-case integrated ownership/migration run. See
[acceptance evidence](sprint-20-acceptance-2026-10-23.md). This addendum does not
turn the assessor's source review into independent test execution or browser QA.

## Coverage added

`Code/Backend/tests/quality/test_sprint20_quality.py` adds nine test functions (14 cases including the six-way stale-eligibility/role parameterization):

| Boundary | Regression evidence encoded |
| --- | --- |
| Target and history scope | Uses the verified private `/organizations/{org_id}/members` roster; rejects a foreign-organization nominee; owner and named nominee see only their organization-scoped history; guests and unrelated roles are denied. |
| Offer authority | Only the current eligible owner can nominate a different active eligible admin in the same approved organization. |
| Acceptance revalidation | Eligibility loss, role change, or inactive membership after the offer prevents acceptance, including with a stale signed-in token. |
| Named decision authority | Only the named nominee can accept; other admins, the former owner, foreign admins, and a mismatched organization path cannot accept. |
| Role-change semantics | Acceptance demotes the former owner to an active member and promotes the admin; it preserves `created_by`, confirmed/waitlisted registrations and existing chat access, and moves queued approval authority to the new owner. |
| Former-owner and retry boundaries | Original request and same-action decision retries do not duplicate audit/notice rows; the former owner can retrieve their original request but cannot accept it or create another offer. |
| Expiry | A fresh app instance projects expiry without writing it; admitting a replacement seals the expired offer with one audit; an accept blocked behind the organization lock rechecks expiry and does not transfer ownership. |
| Concurrent decision | Concurrent accept/revoke yields one terminal decision and exactly one active owner. |

The main-owned `tests/shared/test_sprint20_authorization.py` already covers a manager authorization check using a stale loaded membership; this suite avoids duplicating it. It also does not duplicate migration/index coverage.

## Source review

- `app/domains/ownership/routes.py:17-60` wires the history, create, and decision endpoints. Create explicitly returns HTTP 201; the QA assertions now match that route contract.
- `app/domains/ownership/service.py:171-204` scopes history to the requested organization, limits it to 100 rows, and filters non-owner views to the requesting nominee. `:207-315` checks owner/admin roles and current eligibility under the organization lock, honors the original request key, and seals an expired pending offer before inserting its replacement.
- `app/domains/ownership/service.py:318-456` locks organization then offer and affected memberships, checks the named actor/version, revalidates eligibility and active roles on acceptance, demotes/flushed the former owner before promotion, and records the role and transfer audits plus deduplicated in-app notifications in the same transaction. The path does not call leave/removal workflows.
- Expiry behavior matches the frozen contract: reads project expiry without mutation; a replacement write seals the previous expired offer; a decision checks time after lock acquisition. The after-lock observer clears PostgreSQL's transaction-level statistics snapshot on every poll and matches the waiting query to this test's blocker PID. It still advances the offer expiry only after observing that lock wait, preserving the after-lock expiry proof. A failed expired decision rolls back its attempted seal, so the regression checks rejection and the read projection rather than expecting a durable audit from a rejected request.
- No automated succession behavior was added or tested; it remains outside Sprint 20 scope.

## Verification and limits

- The QA file passed a Python AST parse after the HTTP 201, bounded-wait, and lock-observer snapshot corrections.
- No PostgreSQL test, DB suite, static build, or dependency installation was run by this assessor. The coordinator is running the PostgreSQL suite serially.
- The coordinator reported four runtime/migration passes and verified active-owner uniqueness plus a legacy-duplicate preflight that does not silently repair data. These are coordinator-reported results, not independently reproduced here.
- UI/browser behavior and the final integrated migration/service run are not certified by this review. Treat this as focused backend QA preparation, not a release sign-off.

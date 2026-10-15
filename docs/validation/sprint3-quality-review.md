# Sprint 3 quality review

Reviewed the event routes, schemas, service, existing event tests, and the Sprint 3 draft, discovery, and lifecycle regressions. The review focused on authorization freshness, public/private projections, search and sorting, lifecycle boundaries, database constraints, commit behavior, and the durable registration catch-up seam.

Scope follows `docs/backend/Sprint-3.md` and `docs/backend/Contracts.md`. The canonical Obsidian index still describes prototype-only timing; the explicit 2026-10-13 authorization lifts that timing gate for fictional local work.

## P2 finding: a receipt created against a draft can be admitted after publication

`registrations.service.intake_registration` commits an event-order receipt after checking only that the event exists. `_process_receipt` checks whether the event is published later, when `drain_event` processes the receipt. The publish route does not terminalize pending receipts before making the event public. If the process stops after the intake commit and before the drain, the organizer can publish the draft; a later public read drains the old receipt while the event is published and future-dated, creating a registration for a request made while the event was private.

The regression in `Code/Backend/tests/quality/test_sprint3_quality.py` checks both sides of the boundary: new intake against a draft returns `event_not_found` without creating a receipt, and a pre-existing legacy pending receipt is terminalized as `event_not_found` by publication before any public read drains the queue. It also checks that the public count and registration table remain empty. The invariant is to serialize intake and publication on the event row, reject draft intake before allocating an event order, and close legacy pending receipts in the publication transaction; do not infer eligibility from timestamps or require a schema change. The shared registration seam was reserved for the coordinator, so no production change was made here.

## Other reviewed behavior

The inspected event path rechecks current active manager membership, limits publishing to approved organizations, keeps drafts out of public routes, returns a public projection without creator or attendee identities, escapes SQL `LIKE` metacharacters, composes search with My Clubs, and applies the specified stable sort keys. Event writes use function-scoped database dependencies so commits occur before responses. The added discovery and lifecycle regressions cover venue exclusion, empty memberships, composed filters and tie ordering, ongoing/end boundaries, the registration start boundary, and sanitized malformed paths.

No other concrete defect was established in the inspected Sprint 3 event path. This is a code review, not a claim that the combined Sprint 3 acceptance gate passed.

## Verification status

An AST syntax parse of the owned regression passed. No pytest or live HTTP checker was run by this review. The coordinator owns the combined serial pytest run and root-owned HTTP checker. The new regression is prepared for that gate; its result is not yet known.

## Coordinator resolution

The coordinator reproduced the original regression failure against real PostgreSQL: a public read produced one confirmed registration from a draft-era attempt. The narrow fix adds the published-state predicate to atomic intake and seals legacy pending draft receipts in the publication transaction while the draft event row is locked. Stored rejection outcomes survive retry; neither timestamps nor a schema change are used.

The assessor's final regression and two coordinator additions now pass: **3 passed** in the focused quality gate. They verify no new private-draft admission/order allocation, legacy rejection before public reads and on retries, and rollback of both publication and receipt changes when publication fails. The combined acceptance result is recorded separately in the Sprint 3 handoff.

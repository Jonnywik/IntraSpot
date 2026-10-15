# Sprint 4 quality review

Historical initial review, before the subsequent code-review repairs. Its
NOW-FAILS/UNKNOWN labels describe that earlier snapshot, not current results.
All 13 regression checks passed during Sprint 4 verification on 2026-10-13;
see [repair evidence](code-review-fixes-2026-10-13.md) for the intervening fixes.

Static analysis + code-path proof only. No pytest was run by this review
(venv pydantic install is broken: `ImportError: cannot import name
'BaseModel'`; the coordinator owns the serial run). All production files
treated read-only; only `tests/quality/test_sprint4_quality.py` (new, 13
tests) and this document were written. No commits. No secrets printed.

## Verdicts

| Area | Verdict |
|---|---|
| 1. Capacity races / admission order | PASS (existing threaded coverage holds) |
| 2. Read-path write amplification / unbounded lists / N+1 | **FAIL — D1, D2 (proven)** |
| 3. Published-row integrity / naive datetimes / summary payload | **FAIL — D3, D4 (proven)** |
| 4. Privacy (org exposure, leakage, drafts, post-start withdrawal) | PASS (boundary locks added) |
| 5. Contract drift (routes vs Contracts.md vs openapi.json vs frontend) | PASS on backend surfaces; openapi freshness UNKNOWN (live comparison needs the coordinator run); frontend intentionally static (out of scope, contracts paused) |
| 6. Restart/recovery | PASS (seam intact; multi-seat note below) |

Proven defects: 4 (D1–D4). Speculative concerns investigated and cleared
below; nothing is reported without a code path.

## D1 (High): public GETs perform registration writes

`_public_projection(drain=True)` calls `drain_event`, which opens its own
transaction and processes receipts. Both `GET /events` (`routes.py:175`) and
`GET /events/{event_id}` (`routes.py:187`) build projections with the default
`drain=True`. Reproduction: commit one pending `RegistrationReceipt`
(result None), call either endpoint, re-read the receipt — result is set, a
`Registration` row exists, `confirmed_count` flips 0→1. So an anonymous read
mutates admission state, consumes failure/retry outcomes, and on a hot event
every discovery-list row fans out a lock + drain (`list_events` loops
`_public_projection` per row). Fix direction: remove the drain from the read
path; drain only on intake/submit/withdraw (already covered) and expose
pending state as 503-on-poll or a count computed from committed rows only.
Stubs: `test_public_detail_get_does_not_drain_pending_receipt`,
`test_public_list_get_does_not_drain_pending_receipt` (NOW-FAILS).

## D2 (Medium): unbounded discovery list with per-row N+1 counts

`list_events` has no limit/offset (only `q/sort/my_clubs`), returns all
published-unended rows, and each row costs ≥2 extra SELECTs
(`_drain_event` event lock + `_confirmed_count`; more once D1's drain is
removed, the count query remains per row). Reproduction: insert N events,
`GET /events?limit=2` returns all N (limit ignored → 422-free 200 with full
body); statement counting around two list calls shows SELECT growth linear in
rows. Fix direction: add bounded pagination (`limit` default ~20, max ~100,
plus `offset`/cursor) and compute counts with a single grouped aggregate.
Stubs: `test_event_list_honors_limit`,
`test_event_list_statement_growth_is_bounded` (NOW-FAILS).

## D3 (Medium): unbounded `summary` accepted at publish, served on every row

`Event.summary` is `Text NOT NULL default ''`; `EventDraftInput.summary`
has no `max_length` (unlike title/venue/cost_label), and
`validate_publishable` never checks it. A 100k-char summary publishes 200
and is embedded in full in every `EventPublic` list element — amplifies D2.
Reproduction: draft with 100k summary → `POST publish` → 200. Fix direction:
bound summary at the schema (e.g. `max_length=2000`) and publish validation.
Stub: `test_publish_rejects_oversized_summary` (NOW-FAILS).

## D4 (Medium): published-row integrity is app-only

Migration `mvp_0001` constrains published rows only for
`published_at IS NOT NULL`. NULL title/times/capacity on published rows are
rejected solely by `validate_publishable` at the publish call; any direct
write, fixture path, or future capacity-editing sprint commits rows that
then 500/`ResponseValidationError` the strict `EventPublic` contract
(title/description/times/venue/capacity/banner all non-nullable). The
naive-datetime variant was checked and is NOT a defect: `UTC =
DateTime(timezone=True)` round-trips aware on PostgreSQL/psycopg, and every
write path validates tz-awareness (schema validator + publish checks +
registration `starts_at is None` guard). Reproduction: set a published row's
title (or times) NULL and commit — succeeds today. Fix direction: partial
CHECK constraints (`status != 'published' OR title IS NOT NULL`, same for
description/starts_at/ends_at/venue/capacity/banner) in a new migration.
Stubs: `test_published_null_title_rejected_by_database`,
`test_published_null_times_rejected_by_database` (NOW-FAILS; expect
`IntegrityError`, proving the guard exists).

## Cleared (investigated, no defect)

- **Capacity oversell / double-seat:** intake serializes on the atomic
  `next_admission` bump; drain holds the event lock and processes in
  `event_order`; the partial unique index blocks active duplicates. Covered
  by threaded `test_ten_independent_attempts_obey_three_seat_capacity` and
  `test_different_key_for_active_registration_returns_current_without_a_second_seat`.
- **Gapped `admission_order` in UI position:** duplicate-key receipts consume
  orders without creating registrations, but `_registration_result`
  positions count `Registration` rows with lower orders, never the raw
  order. Locked by `test_admission_order_gaps_do_not_shift_waitlist_positions`.
- **Pending org exposure / creator leakage / drafts:** `GET
  /organizations/{org_id}` returns exactly the five public fields;
  discovery filters `status == 'published'`; drafts 404 on public detail.
  Locked by `test_public_organization_profile_exposes_no_private_ids` and
  `test_pending_and_rejected_org_drafts_are_undiscoverable`.
- **Post-start withdrawal promotion:** denied before mutation; single-seat
  release promotes exactly the earliest entry. Locked by the two withdrawal
  tests. Multi-seat note: publication immutability holds today, so the
  single-promotion path is complete; if capacities ever become editable, one
  promotion per withdrawal under-counts multi-seat releases — loop promotion
  while `confirmed_count < capacity` at that point.
- **Notification dedupe:** `dedupe_key = waitlist_promoted:{registration.id}`
  with a unique constraint, inserted in the withdrawal transaction; double
  withdrawal promotes once. Existing
  `test_pending_receipt_recovers_before_withdrawal_and_promotes_once` covers it.
- **Contract drift:** all 17 `/api/v1` route paths and all 20 schemas exist
  on disk (verified by parsing `docs/backend/openapi.json` directly);
  `banner_key heritage|design|garden|music` consistent across model CHECK,
  schemas, service, Contracts.md, and on-disk openapi. No `features/`,
  `lib/api*` in the frontend — it is intentionally static fixture data
  (`data/events.ts` + `event-artwork.tsx`), and Contracts.md still pauses
  frontend integration, so no drift is claimed. Freshness of the committed
  openapi vs the live app is asserted by
  `test_committed_openapi_matches_live_schema` (outcome UNKNOWN until run).
- **Pending receipt stuck / double promotion:** explicit-NULL receipt stays
  pending and recovers via `drain_event`; crash-between-intake-and-drain
  recovers before withdrawal promotes. Existing tests cover both.

## Serial test request (coordinator: run serially, never concurrent with pytest)

```sh
cd Code/Backend
python -m pytest tests/quality/test_sprint4_quality.py -v
```

Expect 7 failures proving D1–D4 (2 read-path + 2 list + 1 summary + 2
integrity share the D1–D4 roots; exact failing set:
`test_public_detail_get_does_not_drain_pending_receipt`,
`test_public_list_get_does_not_drain_pending_receipt`,
`test_event_list_honors_limit`,
`test_event_list_statement_growth_is_bounded`,
`test_publish_rejects_oversized_summary`,
`test_published_null_title_rejected_by_database`,
`test_published_null_times_rejected_by_database`), 5 passes on the privacy
boundary locks, and 1 openapi-freshness result (pass = docs fresh, fail =
regenerate via `export_openapi.py` and diff). Target DB:
`intraspot_mvp_test` on loopback 5433 via the shared `conftest.py` guard.

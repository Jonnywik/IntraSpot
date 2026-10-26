"""Sprint 27 bounded maintenance behavior on isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent

import pytest
from sqlalchemy import text

from app import maintenance
from app.domains.events.models import Event
from app.domains.registrations import service as registration_service
from app.operations_models import MaintenanceState


@pytest.fixture(autouse=True)
def clear_maintenance_backoff():
    maintenance._clear_pass_retry()
    with maintenance._retry_lock:
        maintenance._retries.clear()
    yield
    maintenance._clear_pass_retry()
    with maintenance._retry_lock:
        maintenance._retries.clear()


def test_pass_is_bounded_and_fair_across_event_and_org_scopes(db, make_org, make_event, monkeypatch):
    organizations = [make_org(), make_org()]
    events = [make_event(org=org) for org in organizations]
    monkeypatch.setattr(maintenance, "_MAX_TARGETS", 2)

    first = maintenance.run_pass()
    assert (first["processed"], first["events_processed"], first["organizations_processed"]) == (2, 1, 1)
    first_event, first_org, _ = maintenance._decode_cursor(db.get(MaintenanceState, "deadline-maintenance").cursor)

    second = maintenance.run_pass()
    assert (second["processed"], second["events_processed"], second["organizations_processed"]) == (2, 1, 1)
    db.expire_all()
    second_event, second_org, _ = maintenance._decode_cursor(db.get(MaintenanceState, "deadline-maintenance").cursor)
    assert first_event in {event.id for event in events} and second_event in {event.id for event in events}
    assert first_org is not None and second_org is not None and first_event != second_event
    assert first_org != second_org
    state = db.get(MaintenanceState, "deadline-maintenance")
    assert state is not None and state.cursor is not None and len(state.cursor) <= 80


def test_event_target_drains_only_one_fifo_batch(db, make_event, monkeypatch):
    event = make_event()
    calls = []

    def drain_once(session, locked_event, *, limit):
        calls.append((locked_event.id, limit))
        return limit

    monkeypatch.setattr(registration_service, "_drain_event_locked", drain_once)
    monkeypatch.setattr(
        registration_service, "catch_up_locked",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("deadlines run before a full receipt batch drains")),
    )

    summary = maintenance.run_pass()
    assert calls == [(event.id, registration_service.DRAIN_BATCH_SIZE)]
    assert summary["receipts_processed"] == registration_service.DRAIN_BATCH_SIZE


def test_concurrent_pass_skips_a_target_already_locked_by_another_pass(make_event, monkeypatch):
    event = make_event()
    entered = ThreadEvent()
    release = ThreadEvent()
    original_drain = registration_service._drain_event_locked
    calls = []

    def slow_drain(session, locked_event, *, limit):
        calls.append(locked_event.id)
        entered.set()
        assert release.wait(timeout=3)
        return original_drain(session, locked_event, limit=limit)

    monkeypatch.setattr(registration_service, "_drain_event_locked", slow_drain)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(maintenance.run_pass)
        assert entered.wait(timeout=3)
        second = maintenance.run_pass()
        release.set()
        first_summary = first.result(timeout=5)

    assert second["skipped_busy"] == 1
    assert second["processed"] == 0
    assert calls == [event.id]
    assert first_summary["events_processed"] == 1


def test_failed_target_rolls_back_and_recovers_after_backoff(db, make_event, monkeypatch):
    event = make_event()
    original_title = event.title
    clock = [100.0]
    monkeypatch.setattr(maintenance, "_monotonic", lambda: clock[0])
    original_drain = registration_service._drain_event_locked
    calls = 0

    def fail_once(session, locked_event, *, limit):
        nonlocal calls
        calls += 1
        if calls == 1:
            locked_event.title = "must roll back"
            raise RuntimeError("private exception text")
        return original_drain(session, locked_event, limit=limit)

    monkeypatch.setattr(registration_service, "_drain_event_locked", fail_once)
    failed = maintenance.run_pass()
    db.expire_all()
    assert db.get(Event, event.id).title == original_title
    assert failed["failed"] == 1
    assert "private exception text" not in str(failed)
    assert db.get(MaintenanceState, "deadline-maintenance").last_error_code == "maintenance_target_failed"

    clock[0] += 31
    recovered = maintenance.run_pass()
    assert recovered["events_processed"] == 1
    assert recovered["failed"] == 0
    assert db.get(MaintenanceState, "deadline-maintenance").last_error_code is None


def test_advisory_trylock_does_not_advance_cursor_or_duplicate_work(db, make_event):
    event = make_event()
    lock_name = f"intraspot.maintenance.e.{event.id}"
    with db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": lock_name})
        busy = maintenance.run_pass()
        assert busy["skipped_busy"] == 1
        assert busy["processed"] == 0
        assert db.get(MaintenanceState, "deadline-maintenance").cursor is None

    retry = maintenance.run_pass()
    assert retry["events_processed"] == 1


def test_budget_exhaustion_advances_poison_target_and_records_partial(db, make_event, monkeypatch):
    make_event()
    make_event()
    clock = [100.0]
    monkeypatch.setattr(maintenance, '_monotonic', lambda: clock[0])
    original = maintenance._process_target
    blocked = []

    def consume_budget(factory, target, cursor, following, deadline):
        if target.scope == 'e' and not blocked:
            blocked.append(target.target_id)
            clock[0] = deadline + .1
            raise maintenance._BudgetExpired
        return original(factory, target, cursor, following, deadline)

    monkeypatch.setattr(maintenance, '_process_target', consume_budget)
    first = maintenance.run_pass()
    assert first['status'] == 'partial' and first['failed'] == 1
    state = db.get(MaintenanceState, 'deadline-maintenance')
    assert state.last_error_code == 'maintenance_budget_exhausted'
    assert maintenance._decode_cursor(state.cursor)[0] == blocked[0]
    clock[0] += 1
    second = maintenance.run_pass()
    assert second['events_processed'] == 1  # Later event still progresses during backoff.

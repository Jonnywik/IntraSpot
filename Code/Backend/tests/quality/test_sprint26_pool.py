"""Six callers can finish nested durable admissions with only five connections."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from types import SimpleNamespace

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session


def test_hosted_requests_leave_capacity_for_durable_reservations(db, monkeypatch):
    from app.core.config import get_settings
    from app.db import session as domain
    bounded = create_engine(get_settings().database_url, pool_size=3, max_overflow=2, pool_timeout=2)
    monkeypatch.setattr(domain, 'engine', lambda: bounded)
    monkeypatch.setattr(domain, 'get_settings', lambda: SimpleNamespace(environment='hosted'))
    barrier, lock = Barrier(3), Lock()
    active = maximum = entered = 0

    @event.listens_for(bounded, 'checkout')
    def checkout(*_):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)

    @event.listens_for(bounded, 'checkin')
    def checkin(*_):
        nonlocal active
        with lock:
            active -= 1

    def request(_):
        nonlocal entered
        scope = domain.get_db()
        try:
            outer = next(scope)
            assert outer.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
            with lock:
                entered += 1
                first = entered <= 3
            if first:
                barrier.wait(timeout=5)
            with Session(bounded) as durable:
                assert durable.scalar(text('SELECT 1')) == 1
            try:
                next(scope)
            except StopIteration:
                pass
            return True
        finally:
            scope.close()

    try:
        with ThreadPoolExecutor(max_workers=6) as workers:
            assert all(workers.map(request, range(6)))
        assert 3 <= maximum <= 5
        assert active == 0
    finally:
        bounded.dispose()

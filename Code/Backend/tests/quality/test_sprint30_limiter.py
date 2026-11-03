from types import SimpleNamespace

import pytest

from app import rate_limits
from app.core.errors import DomainError


def test_full_dispatch_queue_rejects_work_but_leaves_probes_reachable(client, monkeypatch):
    import app.main as main
    from threading import BoundedSemaphore
    slots = BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(main, '_ip_admission_slots', slots)
    monkeypatch.setattr(rate_limits, 'check_ip', lambda request: pytest.fail('No worker dispatch'))
    assert client.get('/health').status_code == 200
    assert client.get('/ready').status_code == 200
    response = client.get('/api/v1/events')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'rate_limit_unavailable'
    slots.release()


def test_full_limiter_queue_fails_closed_before_database_checkout(monkeypatch):
    waits = []
    monkeypatch.setattr(rate_limits, '_owned_limiter_slot', SimpleNamespace(
        acquire=lambda *, timeout: waits.append(timeout) or False,
    ))
    monkeypatch.setattr(rate_limits, 'session_factory', lambda: pytest.fail('No checkout is allowed'))
    with pytest.raises(DomainError) as caught:
        rate_limits._apply_limits([('ip:synthetic', 600)])
    assert (caught.value.code, caught.value.status) == ('rate_limit_unavailable', 503)
    assert waits == [15]


def test_limiter_queue_slot_is_released_after_database_failure(monkeypatch):
    releases = []
    monkeypatch.setattr(rate_limits, '_owned_limiter_slot', SimpleNamespace(
        acquire=lambda *, timeout: True,
        release=lambda: releases.append(True),
    ))

    def unavailable():
        raise RuntimeError('synthetic database outage')

    monkeypatch.setattr(rate_limits, 'session_factory', unavailable)
    with pytest.raises(DomainError) as caught:
        rate_limits._apply_limits([('ip:synthetic', 600)])
    assert caught.value.status == 503
    assert releases == [True]

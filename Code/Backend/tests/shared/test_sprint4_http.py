"""Sprint 4 demonstration through real loopback HTTP, including an API restart.

The shared fixtures guard and populate only intraspot_mvp_test. No development
records, tokens, profile content, or request bodies are printed by this test.
"""

import os
import socket
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import httpx

from app.core.config import ROOT
from app.domains.registrations import service


@contextmanager
def live_api():
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
         '--port', str(port), '--no-access-log', '--log-level', 'warning'],
        cwd=ROOT, env=os.environ.copy(), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url=url, timeout=15, trust_env=False) as client:
            deadline = time.monotonic() + 30
            while True:
                assert process.poll() is None, 'Isolated test API exited before readiness.'
                try:
                    if client.get('/ready').status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline, 'Isolated test API readiness timed out.'
                time.sleep(0.1)
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_http_capacity_promotion_isolation_and_restart(make_event, make_user, token_for):
    event = make_event(capacity=3)
    users = [make_user() for _ in range(10)]
    tokens = {user.id: token_for(user) for user in users}
    keys = {user.id: f'http-sprint4-{index:02d}' for index, user in enumerate(users)}

    def auth(user):
        return {'Authorization': f'Bearer {tokens[user.id]}'}

    with live_api() as client:
        first_instance = client.get('/health').json()['instance_id']
        assert client.get('/api/v1/events').status_code == 200

        def register(user):
            response = client.post(
                f'/api/v1/events/{event.id}/registrations',
                headers=auth(user) | {'Idempotency-Key': keys[user.id]},
            )
            assert response.status_code == 201
            return user, response.json()

        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(register, users))
        ordered = sorted(outcomes, key=lambda item: item[1]['admission_order'])
        assert Counter(row['status'] for _, row in ordered) == {'confirmed': 3, 'waitlisted': 7}
        assert [row['status'] for _, row in ordered] == ['confirmed'] * 3 + ['waitlisted'] * 7
        holder = ordered[0][0]
        promoted, original = ordered[3]
        assert original['waitlist_position'] == 1
        assert original['waitlist_message'] == service.WAITLIST_MESSAGE

        withdrawn = client.delete(
            f'/api/v1/events/{event.id}/registrations/me', headers=auth(holder),
        )
        assert withdrawn.status_code == 200 and withdrawn.json()['status'] == 'cancelled'
        mine = client.get('/api/v1/me/registrations', headers=auth(promoted)).json()
        assert len(mine) == 1 and mine[0]['status'] == 'confirmed'
        notice = client.get('/api/v1/me/notifications', headers=auth(promoted)).json()
        assert len(notice) == 1 and notice[0]['kind'] == 'waitlist_promoted'
        assert client.get('/api/v1/me/notifications', headers=auth(holder)).json() == []
        assert client.get('/api/v1/me/registrations').status_code == 401
        public = client.get(f'/api/v1/events/{event.id}').json()
        assert public['confirmed_count'] == 3 and public['remaining_spots'] == 0
        assert not {'user_id', 'registrations', 'email'} & public.keys()

    # Stop the real server, then prove a new process uses the same durable rows.
    with live_api() as client:
        assert client.get('/health').json()['instance_id'] != first_instance
        replay = client.post(
            f'/api/v1/events/{event.id}/registrations',
            headers=auth(promoted) | {'Idempotency-Key': keys[promoted.id]},
        )
        assert replay.status_code == 201 and replay.json() == original
        assert client.get('/api/v1/me/registrations', headers=auth(promoted)).json()[0]['status'] == 'confirmed'
        assert len(client.get('/api/v1/me/notifications', headers=auth(promoted)).json()) == 1
        retry = client.delete(
            f'/api/v1/events/{event.id}/registrations/me', headers=auth(holder),
        )
        assert retry.status_code == 200 and retry.json() == withdrawn.json()
        assert len(client.get('/api/v1/me/notifications', headers=auth(promoted)).json()) == 1

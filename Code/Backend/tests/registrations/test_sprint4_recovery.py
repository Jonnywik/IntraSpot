"""Prove registration intake survives a real Python process restart."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.domains.events.models import Event
from app.domains.registrations.models import Registration, RegistrationReceipt


BACKEND_ROOT = Path(__file__).resolve().parents[2]
CHILD_TIMEOUT_SECONDS = 30
CHILD_ERROR = re.compile(r'child-error:([A-Za-z][A-Za-z0-9_]*)\s*\Z')

INTAKE_CHILD = r"""
import json
import sys

try:
    from app.core.config import get_settings
    from sqlalchemy.engine import make_url

    settings = get_settings()
    target = make_url(settings.database_url)
    if not (
        settings.environment == 'test'
        and settings.fixture_auth
        and target.database == 'intraspot_mvp_test'
        and target.host in {'127.0.0.1', 'localhost'}
        and target.port == 5433
    ):
        raise RuntimeError('unsafe database target')

    from app.domains.registrations import service

    request = json.load(sys.stdin)
    service.intake_registration(
        request['user_id'], request['event_id'], request['idempotency_key']
    )
    sys.stdout.write(json.dumps({'committed': True}, separators=(',', ':')))
except BaseException as exc:
    sys.stderr.write(f'child-error:{type(exc).__name__}\n')
    raise SystemExit(1)
"""

RECOVERY_CHILD = r"""
import json
import sys

try:
    from app.core.config import get_settings
    from sqlalchemy import func, select
    from sqlalchemy.engine import make_url

    settings = get_settings()
    target = make_url(settings.database_url)
    if not (
        settings.environment == 'test'
        and settings.fixture_auth
        and target.database == 'intraspot_mvp_test'
        and target.host in {'127.0.0.1', 'localhost'}
        and target.port == 5433
    ):
        raise RuntimeError('unsafe database target')

    from app.db.session import session_factory
    from app.domains.events.models import Event
    from app.domains.registrations import service
    from app.domains.registrations.models import Registration, RegistrationReceipt

    request = json.load(sys.stdin)
    service.drain_event(request['event_id'])
    recovered = service.registration_outcome(request['receipt_id'])
    withdrawal = service.withdraw_registration(request['user_id'], request['event_id'])
    retry = service.submit_registration(
        request['user_id'], request['event_id'], request['idempotency_key']
    )

    with session_factory()() as db:
        persisted = db.get(RegistrationReceipt, request['receipt_id'])
        receipt_count = db.scalar(
            select(func.count(RegistrationReceipt.id)).where(
                RegistrationReceipt.user_id == request['user_id'],
                RegistrationReceipt.event_id == request['event_id'],
            )
        )
        registration_count = db.scalar(
            select(func.count(Registration.id)).where(
                Registration.user_id == request['user_id'],
                Registration.event_id == request['event_id'],
            )
        )
        next_admission = db.scalar(
            select(Event.next_admission).where(Event.id == request['event_id'])
        )

    retry_matches_persisted = (
        persisted is not None
        and persisted.processed_at is not None
        and recovered.result == persisted.result == retry.result
        and recovered.http_status == persisted.http_status == retry.http_status
    )
    if not (
        retry_matches_persisted
        and withdrawal.get('status') == 'cancelled'
        and receipt_count == 1
        and registration_count == 1
        and next_admission == 1
    ):
        raise RuntimeError('recovery or retry invariant failed')

    sys.stdout.write(json.dumps({
        'recovered_status': recovered.result.get('status'),
        'recovered_http_status': recovered.http_status,
        'withdrawal_status': withdrawal.get('status'),
        'retry_status': retry.result.get('status'),
        'retry_http_status': retry.http_status,
        'retry_matches_persisted': retry_matches_persisted,
        'receipt_count': receipt_count,
        'registration_count': registration_count,
        'next_admission': next_admission,
    }, separators=(',', ':')))
except BaseException as exc:
    sys.stderr.write(f'child-error:{type(exc).__name__}\n')
    raise SystemExit(1)
"""


def _guarded_test_environment():
    env = os.environ.copy()
    if env.get('ENVIRONMENT') != 'test' or env.get('FIXTURE_AUTH', '').lower() != 'true':
        pytest.fail('Refusing to start subprocess without conftest test settings.', pytrace=False)
    try:
        target = make_url(env['DATABASE_URL'])
    except Exception:
        pytest.fail('Refusing to start subprocess with an invalid database URL.', pytrace=False)
    if not (
        target.drivername == 'postgresql+psycopg'
        and target.database == 'intraspot_mvp_test'
        and target.host in {'127.0.0.1', 'localhost'}
        and target.port == 5433
    ):
        pytest.fail('Refusing to start subprocess outside the guarded test database.', pytrace=False)
    return env


def _run_child(name, code, payload, expected_output_keys):
    try:
        completed = subprocess.run(
            [sys.executable, '-c', code],
            cwd=BACKEND_ROOT,
            env=_guarded_test_environment(),
            input=json.dumps(payload, separators=(',', ':')),
            text=True,
            capture_output=True,
            timeout=CHILD_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_size = len(exc.stdout) if exc.stdout else 0
        stderr_size = len(exc.stderr) if exc.stderr else 0
        pytest.fail(
            f'{name} subprocess timed out after {CHILD_TIMEOUT_SECONDS}s '
            f'(captured stdout={stdout_size} chars, stderr={stderr_size} chars).',
            pytrace=False,
        )
    except OSError as exc:
        pytest.fail(f'{name} subprocess could not start ({type(exc).__name__}).', pytrace=False)

    if completed.returncode != 0:
        match = CHILD_ERROR.fullmatch(completed.stderr)
        diagnostic = f'child error {match.group(1)}' if match else 'no sanitized child diagnostic'
        pytest.fail(
            f'{name} subprocess exited with {completed.returncode} ({diagnostic}; '
            f'captured stdout={len(completed.stdout)} chars).',
            pytrace=False,
        )
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError:
        pytest.fail(
            f'{name} subprocess returned invalid output '
            f'(captured stdout={len(completed.stdout)} chars).',
            pytrace=False,
        )
    if not isinstance(output, dict) or set(output) != expected_output_keys:
        pytest.fail(f'{name} subprocess returned an unexpected output shape.', pytrace=False)
    return output


def test_committed_intake_recovers_after_process_restart(db, make_event, make_user):
    event = make_event(capacity=1)
    attendee = make_user()
    event_id = event.id
    user_id = attendee.id
    idempotency_key = 'sprint4-restart-key-01'

    intake = _run_child(
        'intake',
        INTAKE_CHILD,
        {'user_id': user_id, 'event_id': event_id, 'idempotency_key': idempotency_key},
        {'committed'},
    )
    assert intake['committed'] is True
    db.expire_all()
    pending = db.scalar(
        select(RegistrationReceipt).where(
            RegistrationReceipt.user_id == user_id,
            RegistrationReceipt.event_id == event_id,
            RegistrationReceipt.idempotency_key == idempotency_key,
        )
    )
    assert pending is not None
    receipt_id = pending.id
    assert pending.result is None
    assert pending.http_status is None
    assert pending.processed_at is None
    assert pending.event_order == 1
    assert db.scalar(
        select(func.count(Registration.id)).where(Registration.event_id == event_id)
    ) == 0
    db.rollback()

    recovered = _run_child(
        'recovery',
        RECOVERY_CHILD,
        {
            'user_id': user_id,
            'event_id': event_id,
            'receipt_id': receipt_id,
            'idempotency_key': idempotency_key,
        },
        {
            'recovered_status',
            'recovered_http_status',
            'withdrawal_status',
            'retry_status',
            'retry_http_status',
            'retry_matches_persisted',
            'receipt_count',
            'registration_count',
            'next_admission',
        },
    )
    assert recovered == {
        'recovered_status': 'confirmed',
        'recovered_http_status': 201,
        'withdrawal_status': 'cancelled',
        'retry_status': 'confirmed',
        'retry_http_status': 201,
        'retry_matches_persisted': True,
        'receipt_count': 1,
        'registration_count': 1,
        'next_admission': 1,
    }

    db.expire_all()
    persisted = db.get(RegistrationReceipt, receipt_id)
    registration = db.scalar(
        select(Registration).where(
            Registration.user_id == user_id,
            Registration.event_id == event_id,
        )
    )
    assert persisted is not None
    assert persisted.http_status == 201
    assert persisted.result is not None and persisted.result['status'] == 'confirmed'
    assert persisted.processed_at is not None
    assert registration is not None and registration.status == 'cancelled'
    assert persisted.result['id'] == registration.id
    assert db.scalar(
        select(func.count(RegistrationReceipt.id)).where(
            RegistrationReceipt.user_id == user_id,
            RegistrationReceipt.event_id == event_id,
        )
    ) == 1
    assert db.scalar(
        select(func.count(Registration.id)).where(
            Registration.user_id == user_id,
            Registration.event_id == event_id,
        )
    ) == 1
    assert db.scalar(select(Event.next_admission).where(Event.id == event_id)) == 1

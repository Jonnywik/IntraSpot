"""Integrated Sprint 30 load and recovery checks on isolated PostgreSQL."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, BoundedSemaphore, Lock
from types import SimpleNamespace
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import ROOT, get_settings
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.identity.models import User
from app.domains.organizations.models import Organization, OrgMembership
from app.domains.registrations import service as registration_service
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.main import create_app
from app.notifications import Notification
from app.operations_models import MaintenanceState, RateLimitBucket
from tests.conftest import assert_test_target
from tests.registrations.test_sprint4_recovery import _run_child
from tests.quality.test_sprint27_limits import _enable_test_limits
from tests.quality.test_sprint27_maintenance import clear_maintenance_backoff


SHARED_NAT_IP = "198.51.100.42"
ACTIVE_SESSIONS = 25
CHAT_POLL_ROUNDS = 12

WORKER_FAILURE_CHILD = r"""
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

    from app import maintenance
    from app.db.session import session_factory
    from app.domains.registrations import service
    from app.domains.registrations.models import RegistrationReceipt

    request = json.load(sys.stdin)
    original = service._drain_event_locked

    def fail_target(db, event, *, limit):
        if event.id == request['event_id']:
            raise RuntimeError('simulated worker interruption')
        return original(db, event, limit=limit)

    service._drain_event_locked = fail_target
    summary = maintenance.run_pass()
    with session_factory()() as db:
        receipt = db.get(RegistrationReceipt, request['receipt_id'])
    if summary['failed'] != 1 or receipt is None or receipt.result is not None:
        raise RuntimeError('worker failure did not preserve pending receipt')
    sys.stdout.write(json.dumps({
        'failed': summary['failed'],
        'error_code': summary['error_code'],
        'pending': True,
    }, separators=(',', ':')))
except BaseException as exc:
    sys.stderr.write(f'child-error:{type(exc).__name__}\n')
    raise SystemExit(1)
"""

WORKER_RECOVERY_CHILD = r"""
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

    from app import maintenance
    from app.db.session import session_factory
    from app.domains.registrations.models import RegistrationReceipt

    request = json.load(sys.stdin)
    summary = maintenance.run_pass()
    with session_factory()() as db:
        receipt = db.get(RegistrationReceipt, request['receipt_id'])
    if (
        summary['failed'] != 0
        or summary['events_processed'] != 1
        or receipt is None
        or receipt.result is None
        or receipt.result.get('status') != 'waitlisted'
        or receipt.processed_at is None
    ):
        raise RuntimeError('worker restart did not recover pending receipt')
    sys.stdout.write(json.dumps({
        'failed': summary['failed'],
        'events_processed': summary['events_processed'],
        'recovered_status': receipt.result['status'],
        'processed': receipt.processed_at is not None,
    }, separators=(',', ':')))
except BaseException as exc:
    sys.stderr.write(f'child-error:{type(exc).__name__}\n')
    raise SystemExit(1)
"""


def _auth(token, *, key=None):
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _snapshot_rows(connection, rows):
    snapshot = {}
    for table, identifiers in rows.items():
        snapshot[table] = {
            identity: connection.scalar(
                text(f'SELECT to_jsonb(t)::text FROM "{table}" t WHERE id=:id'),
                {"id": identity},
            )
            for identity in identifiers
        }
        assert all(value is not None for value in snapshot[table].values())
    return snapshot


def test_25_chat_sessions_poll_through_one_nat_without_rate_limit_failures(
    db, make_event, make_user, token_for, monkeypatch
):
    assert_test_target()
    _enable_test_limits(monkeypatch)
    event = make_event(capacity=ACTIVE_SESSIONS)
    users = [make_user() for _ in range(ACTIVE_SESSIONS)]
    tokens = [token_for(user) for user in users]

    for index, user in enumerate(users):
        outcome = registration_service.submit_registration(
            user.id, event.id, f"s30-chat-session-{index:02d}"
        )
        assert outcome.result["status"] == "confirmed"

    from app.db import session as domain

    default_engine = domain.engine()
    db.rollback()
    domain.engine.cache_clear()
    http_engine = None
    listeners_attached = False
    active = maximum = 0
    pool_lock = Lock()

    def checkout(*_):
        nonlocal active, maximum
        with pool_lock:
            active += 1
            maximum = max(maximum, active)

    def checkin(*_):
        nonlocal active
        with pool_lock:
            active -= 1

    chat_url = f"/api/v1/events/{event.id}/chat?limit=50"
    try:
        with monkeypatch.context() as hosted_database:
            # Keep auth and rate-limit settings in fixture test mode; only the
            # engine factory sees the hosted pool profile for these HTTP calls.
            hosted_database.setattr(
                domain,
                "get_settings",
                lambda: SimpleNamespace(
                    environment="hosted",
                    database_url=get_settings().database_url,
                ),
            )
            domain.engine.cache_clear()
            http_engine = domain.engine()
            assert http_engine.pool.size() == 3
            assert http_engine.pool._max_overflow == 2
            sa_event.listen(http_engine.pool, "checkout", checkout)
            sa_event.listen(http_engine.pool, "checkin", checkin)
            listeners_attached = True

            with TestClient(create_app(), client=(SHARED_NAT_IP, 52030)) as browser:
                with ThreadPoolExecutor(max_workers=ACTIVE_SESSIONS) as pool:
                    for _ in range(CHAT_POLL_ROUNDS):
                        responses = list(pool.map(
                            lambda token: browser.get(chat_url, headers=_auth(token)),
                            tokens,
                        ))
                        assert [response.status_code for response in responses] == [200] * ACTIVE_SESSIONS, [
                            response.text for response in responses if response.status_code != 200
                        ]

            assert 0 < maximum <= 5
            assert maximum <= http_engine.pool.size() + http_engine.pool._max_overflow
            assert active == 0
            assert http_engine.pool.checkedout() == 0

        # Twelve rounds model one minute of the visible five-second chat poll without sleeping.
        buckets = list(db.scalars(select(RateLimitBucket.key)))
        assert Counter(key.split(":", 1)[0] for key in buckets) == Counter({
            "ip": 1,
            "account-read": ACTIVE_SESSIONS,
        })
    finally:
        db.rollback()
        if listeners_attached:
            sa_event.remove(http_engine.pool, "checkout", checkout)
            sa_event.remove(http_engine.pool, "checkin", checkin)
        if http_engine is not None:
            http_engine.dispose()
        domain.engine.cache_clear()
        default_engine.dispose()
        restored_engine = domain.engine()
        assert restored_engine.pool.size() == 15
        assert restored_engine.pool._max_overflow == 5


def test_hosted_app_engine_caps_25_request_sessions_at_three_plus_two(db, monkeypatch):
    assert_test_target()
    from app.db import session as domain

    default_engine = domain.engine()
    db.rollback()
    domain.engine.cache_clear()
    app_engine = None
    listeners_attached = False
    active = maximum = entered = nested_entered = 0
    counter_lock = Lock()
    request_barrier = Barrier(3)
    durable_barrier = Barrier(2)
    durable_slots = BoundedSemaphore(2)

    def checkout(*_):
        nonlocal active, maximum
        with counter_lock:
            active += 1
            maximum = max(maximum, active)

    def checkin(*_):
        nonlocal active
        with counter_lock:
            active -= 1

    try:
        with monkeypatch.context() as settings_patch:
            settings_patch.setattr(
                domain,
                "get_settings",
                lambda: SimpleNamespace(
                    environment="hosted",
                    database_url=get_settings().database_url,
                ),
            )
            domain.engine.cache_clear()
            app_engine = domain.engine()
            assert app_engine.pool.size() == 3
            assert app_engine.pool._max_overflow == 2
            sa_event.listen(app_engine.pool, "checkout", checkout)
            sa_event.listen(app_engine.pool, "checkin", checkin)
            listeners_attached = True

            def request(_index):
                nonlocal entered, nested_entered
                scope = domain.get_db()
                try:
                    outer = next(scope)
                    assert outer.scalar(text("SELECT current_database()")) == "intraspot_mvp_test"
                    with counter_lock:
                        entered += 1
                        first_three = entered <= 3
                    if first_three:
                        request_barrier.wait(timeout=5)

                    with durable_slots:
                        # These nested checkouts represent the two connections
                        # reserved for durable admissions beside three requests.
                        with Session(app_engine) as durable:
                            assert durable.scalar(text("SELECT 1")) == 1
                            with counter_lock:
                                nested_entered += 1
                                hold_pair = first_three and nested_entered <= 2
                            if hold_pair:
                                durable_barrier.wait(timeout=5)

                    try:
                        next(scope)
                    except StopIteration:
                        pass
                    return True
                finally:
                    scope.close()

            with ThreadPoolExecutor(max_workers=ACTIVE_SESSIONS) as workers:
                assert all(workers.map(request, range(ACTIVE_SESSIONS)))

            assert maximum == 5
            assert maximum <= app_engine.pool.size() + app_engine.pool._max_overflow
            assert active == 0
            assert app_engine.pool.checkedout() == 0
    finally:
        db.rollback()
        if listeners_attached:
            sa_event.remove(app_engine.pool, "checkout", checkout)
            sa_event.remove(app_engine.pool, "checkin", checkin)
        if app_engine is not None:
            app_engine.dispose()
        domain.engine.cache_clear()
        default_engine.dispose()
        restored_engine = domain.engine()
        assert restored_engine.pool.size() == 15
        assert restored_engine.pool._max_overflow == 5


def test_fresh_s30_database_upgrade_preserves_rows_and_legacy_registration_contract(
    db, token_for, monkeypatch
):
    assert_test_target()
    db.rollback()
    settings = get_settings()
    assert settings.environment == "test" and settings.fixture_auth
    test_url = make_url(settings.database_url)
    assert test_url.drivername == "postgresql+psycopg"
    assert test_url.database == "intraspot_mvp_test"
    assert test_url.host in {"127.0.0.1", "localhost"} and test_url.port == 5433

    scratch_name = f"intraspot_restore_s30_{uuid4().hex}"
    assert scratch_name.startswith("intraspot_restore_s30_")
    loopback_url = test_url.set(host="127.0.0.1", port=5433)
    admin_engine = create_engine(
        loopback_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 2},
    )
    scratch_engine = None
    database_created = False
    try:
        with admin_engine.connect() as admin:
            assert admin.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"),
                {"name": scratch_name},
            ) is None
            admin.execute(text(f'CREATE DATABASE "{scratch_name}"'))
            database_created = True

        scratch_url = loopback_url.set(database=scratch_name)
        scratch_engine = create_engine(
            scratch_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
        scratch_settings = SimpleNamespace(
            environment="test",
            database_url=scratch_url.render_as_string(hide_password=False),
            migration_database_url=None,
        )
        from app.core import config as core_config

        alembic_config = Config(str(ROOT / "alembic.ini"))
        with monkeypatch.context() as migration_settings:
            migration_settings.setattr(
                core_config, "get_settings", lambda: scratch_settings
            )
            command.upgrade(alembic_config, "mvp_0019")

        with scratch_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == scratch_name
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "mvp_0019"

        owner_id, attendee_id, organization_id, membership_id, event_id = (
            uid(), uid(), uid(), uid(), uid()
        )
        created_at = now()
        owner = User(
            id=owner_id,
            email="fictional-s30-rollback-owner@students.plm.edu.ph",
            email_verified=True,
            nickname="Fictional rollback owner",
            age_bracket="18-24",
            tags=["arts"],
            active=True,
            platform_admin=False,
            persona_visible=False,
        )
        attendee = User(
            id=attendee_id,
            email="fictional-s30-rollback-attendee@students.plm.edu.ph",
            email_verified=True,
            nickname="Fictional rollback attendee",
            age_bracket="18-24",
            tags=["arts"],
            active=True,
            platform_admin=False,
            persona_visible=False,
        )
        organization = Organization(
            id=organization_id,
            name="Fictional Sprint 30 rollback society",
            description="Disposable migration rehearsal fixture.",
            accreditation_status="approved",
            created_by=owner_id,
        )
        membership = OrgMembership(
            id=membership_id,
            org_id=organization_id,
            user_id=owner_id,
            role="owner",
            active=True,
        )
        event_start = created_at + timedelta(days=2)
        event = Event(
            id=event_id,
            org_id=organization_id,
            created_by=owner_id,
            title="Fictional Sprint 30 rollback event",
            summary="",
            description="Disposable migration rehearsal fixture.",
            starts_at=event_start,
            ends_at=event_start + timedelta(hours=2),
            venue_name="Fictional campus courtyard",
            venue_address="Fictional local address",
            capacity=3,
            banner_key="heritage",
            cost_label="Free",
            status="published",
            registration_mode="instant",
            event_type="scheduled",
            published_at=created_at,
            next_admission=0,
            interest_count=0,
        )
        with Session(scratch_engine, expire_on_commit=False) as seed:
            seed.add_all([owner, attendee])
            seed.flush()
            seed.add(organization)
            seed.flush()
            seed.add_all([membership, event])
            seed.commit()

        fictional_rows = {
            "users": (owner_id, attendee_id),
            "organizations": (organization_id,),
            "org_memberships": (membership_id,),
            "events": (event_id,),
        }
        with scratch_engine.connect() as connection:
            before_head = _snapshot_rows(connection, fictional_rows)

        with monkeypatch.context() as migration_settings:
            migration_settings.setattr(
                core_config, "get_settings", lambda: scratch_settings
            )
            command.upgrade(alembic_config, "head")

        with scratch_engine.connect() as connection:
            version = connection.scalar(text("SELECT version_num FROM alembic_version"))
            after_head = _snapshot_rows(connection, fictional_rows)
        assert version == ScriptDirectory.from_config(
            Config(str(ROOT / "alembic.ini"))
        ).get_current_head()
        assert after_head == before_head

        attendee_token = token_for(attendee_id)
        from app.db import session as domain
        import app.main as main_module

        api_settings = SimpleNamespace(environment="test")
        with monkeypatch.context() as app_database:
            app_database.setattr(domain, "engine", lambda: scratch_engine)
            app_database.setattr(domain, "get_settings", lambda: api_settings)
            app_database.setattr(main_module, "engine", lambda: scratch_engine)
            with TestClient(create_app()) as api_client:
                readiness = api_client.get("/ready")
                assert readiness.status_code == 200
                assert readiness.json() == {"status": "ready"}
                path = f"/api/v1/events/{event_id}/registrations"
                headers = _auth(attendee_token, key="s30-legacy-contract-001")
                first = api_client.post(path, headers=headers, json={})
                assert first.status_code == 201, first.text
                assert first.json()["status"] == "confirmed"

                # This is the mvp_0019 registration HTTP contract on HEAD, not a
                # claim that the historical mvp_0019 application artifact is ready.
                retry = api_client.post(path, headers=headers, json={})
                assert retry.status_code == 201
                assert retry.json() == first.json()

        with scratch_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT count(*) FROM registration_receipts WHERE event_id=:id"),
                {"id": event_id},
            ) == 1
            assert connection.scalar(
                text("SELECT count(*) FROM registrations WHERE event_id=:id"),
                {"id": event_id},
            ) == 1
    finally:
        try:
            db.rollback()
        finally:
            try:
                if scratch_engine is not None:
                    scratch_engine.dispose()
            finally:
                try:
                    if database_created:
                        with admin_engine.connect() as admin:
                            admin.execute(text(f'DROP DATABASE "{scratch_name}"'))
                finally:
                    admin_engine.dispose()


def test_registration_burst_recovers_worker_failure_and_promotes_fifo(
    db, make_event, make_user, token_for, monkeypatch, clear_maintenance_backoff
):
    assert_test_target()
    _enable_test_limits(monkeypatch)
    event = make_event(capacity=3)
    users = [make_user() for _ in range(11)]
    attempts = [
        {"user": user, "token": token_for(user), "key": f"s30-burst-{index:02d}"}
        for index, user in enumerate(users[:10])
    ]

    with TestClient(create_app(), client=(SHARED_NAT_IP, 52030)) as browser:
        def submit(attempt):
            return browser.post(
                f"/api/v1/events/{event.id}/registrations",
                headers=_auth(attempt["token"], key=attempt["key"]),
                json={},
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(submit, attempts))

        assert [response.status_code for response in responses] == [201] * 10, [
            response.text for response in responses if response.status_code != 201
        ]
        submitted = [
            {**attempt, "result": response.json()}
            for attempt, response in zip(attempts, responses)
        ]
        assert Counter(item["result"]["status"] for item in submitted) == Counter({
            "confirmed": 3,
            "waitlisted": 7,
        })
        ordered = sorted(submitted, key=lambda item: item["result"]["admission_order"])
        assert [item["result"]["status"] for item in ordered] == ["confirmed"] * 3 + ["waitlisted"] * 7
        waiters = [item for item in ordered if item["result"]["status"] == "waitlisted"]
        assert [item["result"]["waitlist_position"] for item in waiters] == list(range(1, 8))

        for attempt, original in zip(attempts, responses):
            retry = submit(attempt)
            assert retry.status_code == 201
            assert retry.json() == original.json()

        db.expire_all()
        receipts = list(db.scalars(
            select(RegistrationReceipt)
            .where(RegistrationReceipt.event_id == event.id)
            .order_by(RegistrationReceipt.event_order)
        ))
        assert len(receipts) == 10
        assert [receipt.event_order for receipt in receipts] == list(range(1, 11))
        assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 10
        assert db.scalar(select(func.count(Registration.id)).where(
            Registration.event_id == event.id,
            Registration.status == "confirmed",
        )) == event.capacity

        # Model a request durably accepted just before its process stops.
        pending_id = registration_service.intake_registration(
            users[10].id, event.id, "s30-worker-recovery-11"
        )
        db.rollback()
        failed = _run_child(
            "worker failure",
            WORKER_FAILURE_CHILD,
            {"event_id": event.id, "receipt_id": pending_id},
            {"failed", "error_code", "pending"},
        )
        assert failed == {
            "failed": 1,
            "error_code": "maintenance_target_failed",
            "pending": True,
        }
        db.expire_all()
        assert db.get(RegistrationReceipt, pending_id).result is None
        assert db.get(MaintenanceState, "deadline-maintenance").last_error_code == "maintenance_target_failed"

        recovered = _run_child(
            "worker restart recovery",
            WORKER_RECOVERY_CHILD,
            {"receipt_id": pending_id},
            {"failed", "events_processed", "recovered_status", "processed"},
        )
        assert recovered == {
            "failed": 0,
            "events_processed": 1,
            "recovered_status": "waitlisted",
            "processed": True,
        }
        db.expire_all()
        pending = db.get(RegistrationReceipt, pending_id)
        assert pending.processed_at is not None
        assert pending.result["status"] == "waitlisted"

        holder = next(item for item in ordered if item["result"]["status"] == "confirmed")
        first_waiter = waiters[0]
        withdrawal = browser.delete(
            f"/api/v1/events/{event.id}/registrations/me",
            headers=_auth(holder["token"]),
        )
        assert withdrawal.status_code == 200
        assert withdrawal.json()["status"] == "cancelled"

        current = browser.get(
            "/api/v1/me/registrations",
            headers=_auth(first_waiter["token"]),
        )
        assert current.status_code == 200
        promoted = next(
            item for item in current.json() if item["id"] == first_waiter["result"]["id"]
        )
        assert promoted["status"] == "confirmed"

        # The original key remains an immutable replay after the FIFO state changes.
        promoted_retry = submit(first_waiter)
        assert promoted_retry.status_code == 201
        assert promoted_retry.json() == first_waiter["result"]
        assert promoted_retry.json()["status"] == "waitlisted"

    db.expire_all()
    registrations = list(db.scalars(
        select(Registration).where(Registration.event_id == event.id)
    ))
    assert Counter(registration.status for registration in registrations) == Counter({
        "confirmed": 3,
        "waitlisted": 7,
        "cancelled": 1,
    })
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 11
    assert db.scalar(select(func.count(RegistrationReceipt.id)).where(
        RegistrationReceipt.event_id == event.id
    )) == 11
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.event_id == event.id,
        Notification.kind == "waitlist_promoted",
    )) == 1

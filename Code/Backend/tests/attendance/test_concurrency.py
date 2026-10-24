from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import uid
from app.db.session import engine
from app.domains.attendance import service
from app.domains.attendance.models import AttendanceAudit, AttendanceMark, AttendanceSession
from app.domains.attendance.schemas import AttendanceMarkInput, AttendanceSessionInput
from app.domains.organizations.models import OrgMembership, Organization


def run_race(barrier, operation):
    barrier.wait(timeout=15)
    with Session(engine(), expire_on_commit=False) as concurrent_db:
        try:
            result = operation(concurrent_db)
            concurrent_db.commit()
            return ("ok", result)
        except DomainError as exc:
            concurrent_db.rollback()
            return ("error", exc.status, exc.code)
        except Exception:
            concurrent_db.rollback()
            raise


def test_concurrent_same_actor_key_replays_one_stored_command(
    db, make_org, make_event,
):
    org = make_org()
    event = make_event(org=org)
    request = AttendanceSessionInput(
        is_open=True, version=0, client_key=uuid4(),
    )
    barrier = Barrier(2)

    def submit(concurrent_db):
        return service.set_attendance_session(
            concurrent_db, org.created_by, event.id, request,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _: run_race(barrier, submit), range(2),
        ))

    assert results[0] == results[1]
    assert results[0][0] == "ok"
    db.expire_all()
    assert db.get(AttendanceSession, event.id).version == 1
    assert db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.event_id == event.id,
    )) == 1


def test_concurrent_close_and_mark_serialize_with_one_stale_version(
    db, make_org, make_event, make_registration,
):
    org = make_org()
    event = make_event(org=org)
    registration, _ = make_registration(event)
    opened = service.set_attendance_session(
        db,
        org.created_by,
        event.id,
        AttendanceSessionInput(is_open=True, version=0, client_key=uuid4()),
    )
    db.commit()
    assert opened["version"] == 1

    close_request = AttendanceSessionInput(
        is_open=False, version=1, client_key=uuid4(),
    )
    mark_request = AttendanceMarkInput(
        attended=True, version=1, client_key=uuid4(),
    )
    barrier = Barrier(2)

    def close(concurrent_db):
        return service.set_attendance_session(
            concurrent_db, org.created_by, event.id, close_request,
        )

    def mark(concurrent_db):
        return service.set_registration_attendance(
            concurrent_db, org.created_by, event.id, registration.id, mark_request,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(run_race, barrier, close),
            pool.submit(run_race, barrier, mark),
        ]
        outcomes = [future.result() for future in results]

    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert sum(outcome[0] == "error" and outcome[1:] == (
        409, "attendance_version_conflict",
    ) for outcome in outcomes) == 1
    db.expire_all()
    assert db.get(AttendanceSession, event.id).version == 2
    assert db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.event_id == event.id,
    )) == 2
    mark_row = db.get(AttendanceMark, registration.id)
    if mark_row is not None:
        assert mark_row.attended is True
        assert db.get(AttendanceSession, event.id).is_open is True
    else:
        assert db.get(AttendanceSession, event.id).is_open is False


def test_concurrent_role_revocation_is_rechecked_before_retry(
    db, make_user, make_org, make_event,
):
    org = make_org()
    event = make_event(org=org)
    admin = make_user()
    membership = OrgMembership(
        id=uid(), org_id=org.id, user_id=admin.id, role="admin", active=True,
    )
    db.add(membership)
    db.commit()
    request = AttendanceSessionInput(
        is_open=True, version=0, client_key=uuid4(),
    )
    barrier = Barrier(2)

    def write(concurrent_db):
        return service.set_attendance_session(
            concurrent_db, admin.id, event.id, request,
        )

    def revoke(concurrent_db):
        concurrent_db.scalar(
            select(Organization)
            .where(Organization.id == org.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current_membership = concurrent_db.scalar(
            select(OrgMembership)
            .where(OrgMembership.id == membership.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current_membership.active = False
        return {"revoked": True}

    with ThreadPoolExecutor(max_workers=2) as pool:
        write_future = pool.submit(run_race, barrier, write)
        revoke_future = pool.submit(run_race, barrier, revoke)
        write_outcome = write_future.result()
        revoke_outcome = revoke_future.result()

    assert revoke_outcome == ("ok", {"revoked": True})
    assert write_outcome[0] == "ok" or write_outcome[1:] == (
        403, "organization_forbidden",
    )
    db.expire_all()
    assert db.get(OrgMembership, membership.id).active is False

    with pytest.raises(DomainError) as exc:
        service.set_attendance_session(db, admin.id, event.id, request)
    assert (exc.value.status, exc.value.code) == (403, "organization_forbidden")
    db.rollback()
    assert db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.actor_id == admin.id,
        AttendanceAudit.client_key == str(request.client_key),
    )) in (0, 1)

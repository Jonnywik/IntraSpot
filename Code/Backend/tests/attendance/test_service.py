from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.attendance import service
from app.domains.attendance.models import AttendanceAudit, AttendanceMark, AttendanceSession
from app.domains.attendance.schemas import AttendanceMarkInput, AttendanceSessionInput
from app.domains.events.models import Event
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration


def add_staff(db, org, user, role):
    membership = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=True,
    )
    db.add(membership)
    db.commit()
    return membership


def test_roster_is_confirmed_only_opaque_and_read_only(
    db, make_org, make_event, make_registration,
):
    org = make_org()
    actor_id = org.created_by
    event = make_event(org=org)
    confirmed_later, later_user = make_registration(
        event, status="confirmed", admission_order=8,
    )
    confirmed_first, first_user = make_registration(
        event, status="confirmed", admission_order=3,
    )
    excluded = [
        make_registration(event, status=status, admission_order=index + 10)[0]
        for index, status in enumerate((
            "pending", "waitlisted", "reconfirmation_required", "cancelled", "rejected",
        ))
    ]
    db.add_all([
        AttendanceMark(registration_id=confirmed_later.id, attended=True),
        AttendanceMark(registration_id=excluded[3].id, attended=True),
    ])
    db.commit()
    registration_state = db.execute(
        select(Registration.id, Registration.status, Registration.admission_order)
        .where(Registration.event_id == event.id)
        .order_by(Registration.id)
    ).all()

    result = service.get_attendance(db, actor_id, event.id)

    assert [row["registration_id"] for row in result["attendees"]] == [
        confirmed_first.id, confirmed_later.id,
    ]
    assert result["confirmed_count"] == 2
    assert result["checked_in_count"] == 1
    assert result["is_open"] is False
    assert result["version"] == 0
    assert result["writable"] is True
    by_id = {row["registration_id"]: row for row in result["attendees"]}
    assert by_id[confirmed_first.id]["attended"] is False
    assert by_id[confirmed_later.id]["attended"] is True
    for registration, user in (
        (confirmed_first, first_user), (confirmed_later, later_user),
    ):
        label = by_id[registration.id]["participant_label"]
        assert registration.id in label
        assert user.id not in label
        assert user.email not in label
        assert user.nickname not in label
    assert not any(row["registration_id"] in {item.id for item in excluded}
                   for row in result["attendees"])
    assert service.list_attendance_history(db, actor_id, event.id) == []
    assert db.scalar(select(func.count(AttendanceSession.event_id))) == 0
    assert db.scalar(select(func.count(AttendanceMark.registration_id))) == 2
    assert db.execute(
        select(Registration.id, Registration.status, Registration.admission_order)
        .where(Registration.event_id == event.id)
        .order_by(Registration.id)
    ).all() == registration_state


def test_only_active_same_organization_staff_can_read_attendance(
    db, make_user, make_org, make_event,
):
    org = make_org()
    event = make_event(org=org)
    member = make_user()
    inactive_admin = make_user()
    ineligible_admin = make_user(
        email="attendance-ineligible@example.org", email_verified=False,
    )
    add_staff(db, org, member, "member")
    inactive = add_staff(db, org, inactive_admin, "admin")
    add_staff(db, org, ineligible_admin, "admin")
    inactive.active = False
    db.commit()
    other_owner = make_user()
    other_org = make_org(owner=other_owner)

    for actor_id in (member.id, inactive_admin.id, ineligible_admin.id, other_owner.id):
        with pytest.raises(DomainError) as exc:
            service.get_attendance(db, actor_id, event.id)
        assert exc.value.status == 403
        db.rollback()


def test_after_end_writes_are_idempotent_audited_and_versioned(
    db, make_org, make_event, make_registration,
):
    org = make_org()
    actor_id = org.created_by
    event = make_event(
        org=org,
        starts_at=now() - timedelta(hours=3),
        ends_at=now() - timedelta(hours=2),
    )
    original_capacity, original_next_admission = event.capacity, event.next_admission
    registration, _ = make_registration(event)
    open_request = AttendanceSessionInput(
        is_open=True, version=0, client_key=uuid4(),
    )

    opened = service.set_attendance_session(db, actor_id, event.id, open_request)
    db.commit()
    assert opened["is_open"] is True
    assert opened["version"] == 1
    assert service.set_attendance_session(db, actor_id, event.id, open_request) == opened
    db.commit()

    mark_request = AttendanceMarkInput(
        attended=True, version=1, client_key=uuid4(),
    )
    marked = service.set_registration_attendance(
        db, actor_id, event.id, registration.id, mark_request,
    )
    db.commit()
    assert marked["version"] == 2
    assert service.set_registration_attendance(
        db, actor_id, event.id, registration.id, mark_request,
    ) == marked
    db.commit()

    correction = AttendanceMarkInput(
        attended=False, version=2, client_key=uuid4(),
    )
    cleared = service.set_registration_attendance(
        db, actor_id, event.id, registration.id, correction,
    )
    db.commit()
    assert cleared["attended"] is False
    assert cleared["version"] == 3
    assert db.get(AttendanceMark, registration.id).attended is False
    unchanged_registration = db.get(Registration, registration.id)
    assert (unchanged_registration.status, unchanged_registration.admission_order) == (
        "confirmed", 1,
    )
    unchanged_event = db.get(Event, event.id)
    assert (unchanged_event.capacity, unchanged_event.next_admission) == (
        original_capacity, original_next_admission,
    )

    with pytest.raises(DomainError) as exc:
        service.set_registration_attendance(
            db,
            actor_id,
            event.id,
            registration.id,
            AttendanceMarkInput(
                attended=True, version=2, client_key=correction.client_key,
            ),
        )
    assert (exc.value.code, exc.value.status) == ("attendance_client_key_reused", 409)
    db.rollback()

    with pytest.raises(DomainError) as exc:
        service.set_registration_attendance(
            db,
            actor_id,
            event.id,
            registration.id,
            AttendanceMarkInput(attended=True, version=2, client_key=uuid4()),
        )
    assert (exc.value.code, exc.value.status) == ("attendance_version_conflict", 409)
    db.rollback()

    assert db.get(AttendanceSession, event.id).version == 3
    assert db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.event_id == event.id,
    )) == 3
    history = service.list_attendance_history(db, actor_id, event.id)
    assert len(history) == 3
    assert {row["action"] for row in history} == {"session", "mark"}
    assert all(row["actor_id"] == actor_id for row in history)


def test_closed_checkin_and_nonconfirmed_registration_reject_marks(
    db, make_org, make_event, make_registration,
):
    org = make_org()
    event = make_event(org=org)
    confirmed, _ = make_registration(event, admission_order=1)
    pending, _ = make_registration(event, status="pending", admission_order=2)

    with pytest.raises(DomainError) as exc:
        service.set_registration_attendance(
            db,
            org.created_by,
            event.id,
            confirmed.id,
            AttendanceMarkInput(attended=True, version=0, client_key=uuid4()),
        )
    assert (exc.value.code, exc.value.status) == ("attendance_checkin_closed", 409)
    db.rollback()

    opened = service.set_attendance_session(
        db,
        org.created_by,
        event.id,
        AttendanceSessionInput(is_open=True, version=0, client_key=uuid4()),
    )
    db.commit()
    assert opened["version"] == 1
    with pytest.raises(DomainError) as exc:
        service.set_registration_attendance(
            db,
            org.created_by,
            event.id,
            pending.id,
            AttendanceMarkInput(attended=True, version=1, client_key=uuid4()),
        )
    assert (exc.value.code, exc.value.status) == (
        "attendance_registration_unavailable", 409,
    )
    db.rollback()
    assert db.get(AttendanceSession, event.id).version == 1
    assert db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.event_id == event.id,
    )) == 1


def test_current_staff_authority_is_checked_before_stored_retry(
    db, make_user, make_org, make_event,
):
    org = make_org()
    event = make_event(org=org)
    admin = make_user()
    membership = add_staff(db, org, admin, "admin")
    request = AttendanceSessionInput(
        is_open=True, version=0, client_key=uuid4(),
    )
    original = service.set_attendance_session(db, admin.id, event.id, request)
    db.commit()

    membership.active = False
    db.commit()
    with pytest.raises(DomainError) as exc:
        service.set_attendance_session(db, admin.id, event.id, request)
    assert (exc.value.code, exc.value.status) == ("organization_forbidden", 403)
    db.rollback()
    assert db.get(AttendanceSession, event.id).version == original["version"]
    assert db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.client_key == str(request.client_key),
    )) == 1


@pytest.mark.parametrize(
    ("accreditation_status", "event_status", "expected_error"),
    (
        ("pending", "published", ("organization_not_approved", 403)),
        ("approved", "draft", ("attendance_event_not_writable", 409)),
    ),
)
def test_write_gate_fails_closed_for_unapproved_or_unpublished(
    db, make_org, make_event, accreditation_status, event_status, expected_error,
):
    org = make_org(accreditation_status=accreditation_status)
    event = make_event(org=org, status=event_status)
    if accreditation_status == "approved":
        assert service.get_attendance(db, org.created_by, event.id)["writable"] is False

    with pytest.raises(DomainError) as exc:
        service.set_attendance_session(
            db,
            org.created_by,
            event.id,
            AttendanceSessionInput(
                is_open=True, version=0, client_key=uuid4(),
            ),
        )
    assert (exc.value.code, exc.value.status) == expected_error
    db.rollback()
    assert db.scalar(select(func.count(AttendanceAudit.id))) == 0

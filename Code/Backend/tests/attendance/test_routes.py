from uuid import uuid4

from sqlalchemy import func, select

from app.db.models import uid
from app.domains.attendance.models import AttendanceAudit, AttendanceSession
from app.domains.organizations.models import OrgMembership


def add_staff(db, org, user, role):
    db.add(OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=True,
    ))
    db.commit()


def authorization(token):
    return {"Authorization": f"Bearer {token}"}


def test_routes_are_protected_and_limited_to_same_org_staff(
    client, db, make_user, make_org, make_event, make_registration, token_for,
):
    owner = make_user(nickname="Staff owner")
    org = make_org(owner=owner)
    event = make_event(org=org)
    registration, attendee = make_registration(event)
    admin, moderator, member = (make_user() for _ in range(3))
    add_staff(db, org, admin, "admin")
    add_staff(db, org, moderator, "moderator")
    add_staff(db, org, member, "member")
    other_owner = make_user()
    make_org(owner=other_owner)
    path = f"/api/v1/events/{event.id}/attendance"

    assert client.get(path).status_code == 401
    owner_response = client.get(path, headers=authorization(token_for(owner)))
    assert owner_response.status_code == 200
    result = owner_response.json()
    assert result["confirmed_count"] == 1
    attendee_row = result["attendees"][0]
    assert registration.id in attendee_row["participant_label"]
    assert attendee.id not in attendee_row["participant_label"]
    assert attendee.email not in attendee_row["participant_label"]
    for staff in (admin, moderator):
        assert client.get(path, headers=authorization(token_for(staff))).status_code == 200
    assert client.get(path, headers=authorization(token_for(member))).status_code == 403
    assert client.get(path, headers=authorization(token_for(other_owner))).status_code == 403


def test_mutation_routes_enforce_strict_extra_forbidden_inputs(
    client, db, make_org, make_event, token_for,
):
    org = make_org()
    event = make_event(org=org)
    headers = authorization(token_for(org.created_by))
    path = f"/api/v1/events/{event.id}/attendance/session"

    wrong_type = client.post(path, headers=headers, json={
        "is_open": 1, "version": 0, "client_key": str(uuid4()),
    })
    extra_field = client.post(path, headers=headers, json={
        "is_open": True,
        "version": 0,
        "client_key": str(uuid4()),
        "comment": "not part of the contract",
    })
    assert wrong_type.status_code == 422
    assert extra_field.status_code == 422
    assert db.get(AttendanceSession, event.id) is None
    assert db.scalar(select(func.count(AttendanceAudit.id))) == 0

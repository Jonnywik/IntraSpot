"""Independent Sprint 21 HTTP boundary checks; execute only in the serial DB slot."""
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.db.models import now, uid
from app.domains.attendance.models import AttendanceAudit, AttendanceMark
from app.domains.chat.models import ChatMessage
from app.domains.events.models import Event
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _add_membership(db, org, user, role="member", active=True):
    grant = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=active,
    )
    db.add(grant)
    db.commit()
    return grant


def _seed_registration(db, event, user, status):
    previous = db.scalar(
        select(func.max(Registration.admission_order)).where(
            Registration.event_id == event.id,
        )
    ) or 0
    registration = Registration(
        id=uid(), user_id=user.id, event_id=event.id, status=status,
        admission_order=previous + 1,
        confirmed_at=now() if status == "confirmed" else None,
    )
    db.add(registration)
    db.commit()
    return registration


def _set_session(client, token, event_id, is_open, version, client_key):
    return client.post(
        f"/api/v1/events/{event_id}/attendance/session",
        headers=_auth(token),
        json={"is_open": is_open, "version": version, "client_key": str(client_key)},
    )


def _mark(client, token, event_id, registration_id, attended, version, client_key):
    return client.put(
        f"/api/v1/events/{event_id}/attendance/registrations/{registration_id}",
        headers=_auth(token),
        json={"attended": attended, "version": version, "client_key": str(client_key)},
    )


def test_staff_roster_is_private_confirmed_only_and_available_after_event_end(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    admin = make_user()
    moderator = make_user()
    ordinary = make_user()
    _add_membership(db, org, admin, role="admin")
    _add_membership(db, org, moderator, role="moderator")
    _add_membership(db, org, ordinary)

    foreign_owner = make_user()
    foreign_org = make_org(owner=foreign_owner)
    foreign_admin = make_user()
    _add_membership(db, foreign_org, foreign_admin, role="admin")
    platform_admin = make_user(platform_admin=True)

    event = make_event(
        org=org,
        starts_at=now() - timedelta(hours=3),
        ends_at=now() - timedelta(hours=1),
    )
    confirmed_person = make_user(
        email="attendance-private-fixture@example.invalid",
        nickname="ATTENDANCE PRIVATE NICKNAME",
    )
    confirmed = _seed_registration(db, event, confirmed_person, "confirmed")
    for status in (
        "pending", "waitlisted", "reconfirmation_required", "cancelled", "rejected",
    ):
        _seed_registration(db, event, make_user(), status)

    other_event = make_event(org=org)
    other_event_registration = _seed_registration(
        db, other_event, make_user(), "confirmed",
    )

    event_url = f"/api/v1/events/{event.id}/attendance"
    for staff in (owner, admin, moderator):
        headers = _auth(token_for(staff))
        state = client.get(event_url, headers=headers)
        history = client.get(f"{event_url}/history", headers=headers)
        assert state.status_code == 200
        assert history.status_code == 200
        body = state.json()
        assert set(body) == {
            "event_id", "is_open", "version", "writable", "confirmed_count",
            "checked_in_count", "attendees",
        }
        assert body["is_open"] is False
        assert body["version"] == 0
        assert body["writable"] is True
        assert body["confirmed_count"] == 1
        assert [row["registration_id"] for row in body["attendees"]] == [confirmed.id]
        attendee_row = body["attendees"][0]
        assert set(attendee_row) == {"registration_id", "participant_label", "attended"}
        assert attendee_row["participant_label"] == f"Registration · {confirmed.id}"
        assert confirmed_person.email not in state.text
        assert confirmed_person.nickname not in state.text
        assert confirmed_person.id not in state.text
        assert confirmed_person.email not in history.text
        assert confirmed_person.nickname not in history.text
        assert confirmed_person.id not in history.text

    for denied_user in (ordinary, foreign_admin, platform_admin):
        headers = _auth(token_for(denied_user))
        assert client.get(event_url, headers=headers).status_code == 403
        assert client.get(f"{event_url}/history", headers=headers).status_code == 403
    assert client.get(event_url).status_code == 401
    assert client.get(f"{event_url}/history").status_code == 401

    closed_mark = _mark(
        client, token_for(owner), event.id, confirmed.id, True, 0, uuid4(),
    )
    assert closed_mark.status_code == 409
    assert closed_mark.json()["error"]["code"] == "attendance_checkin_closed"

    opened = _set_session(client, token_for(owner), event.id, True, 0, uuid4())
    assert opened.status_code == 200
    mismatched = _mark(
        client, token_for(admin), event.id, other_event_registration.id,
        True, 1, uuid4(),
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["error"]["code"] == "attendance_registration_unavailable"
    marked = _mark(client, token_for(admin), event.id, confirmed.id, True, 1, uuid4())
    assert marked.status_code == 200
    closed = _set_session(client, token_for(moderator), event.id, False, 2, uuid4())
    assert closed.status_code == 200
    stale = _set_session(client, token_for(owner), event.id, True, 2, uuid4())
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "attendance_version_conflict"

    current = client.get(event_url, headers=_auth(token_for(owner))).json()
    assert current["version"] == 3
    assert current["is_open"] is False
    assert current["checked_in_count"] == 1


def test_former_owner_cannot_replay_attendance_after_ownership_transfer(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    nominee = make_user()
    _add_membership(db, org, nominee, role="admin")
    event = make_event(org=org)
    owner_token = token_for(owner)
    nominee_token = token_for(nominee)
    key = uuid4()

    original = _set_session(client, owner_token, event.id, True, 0, key)
    assert original.status_code == 200
    replay_while_authorized = _set_session(
        client, owner_token, event.id, True, 0, key,
    )
    assert replay_while_authorized.status_code == 200
    assert replay_while_authorized.json() == original.json()
    reused_key = _set_session(client, owner_token, event.id, False, 1, key)
    assert reused_key.status_code == 409
    assert reused_key.json()["error"]["code"] == "attendance_client_key_reused"

    offer = client.post(
        f"/api/v1/organizations/{org.id}/ownership-transfers",
        headers=_auth(owner_token),
        json={"nominee_id": nominee.id, "client_key": str(uuid4())},
    )
    assert offer.status_code == 201
    decision = client.post(
        f"/api/v1/organizations/{org.id}/ownership-transfers/{offer.json()['id']}/decision",
        headers=_auth(nominee_token),
        json={"action": "accept", "version": 1},
    )
    assert decision.status_code == 200

    db.expire_all()
    former_owner_grant = db.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org.id,
            OrgMembership.user_id == owner.id,
        )
    )
    assert (former_owner_grant.role, former_owner_grant.active) == ("member", True)

    retry_after_transfer = _set_session(
        client, owner_token, event.id, True, 0, key,
    )
    assert retry_after_transfer.status_code == 403
    assert client.get(
        f"/api/v1/events/{event.id}/attendance/history",
        headers=_auth(owner_token),
    ).status_code == 403

    new_owner_state = client.get(
        f"/api/v1/events/{event.id}/attendance",
        headers=_auth(nominee_token),
    )
    assert new_owner_state.status_code == 200
    assert new_owner_state.json()["version"] == 1
    assert db.scalar(
        select(func.count(AttendanceAudit.id)).where(
            AttendanceAudit.event_id == event.id,
        )
    ) == 1


def test_registration_cancellation_retains_mark_but_removes_it_from_current_counts(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, capacity=3)
    withdrawing_attendee = make_user()
    remaining_attendee = make_user()

    created = []
    for attendee, key in (
        (withdrawing_attendee, "s21-withdraw-attendee"),
        (remaining_attendee, "s21-remaining-attendee"),
    ):
        response = client.post(
            f"/api/v1/events/{event.id}/registrations",
            headers={
                **_auth(token_for(attendee)),
                "Idempotency-Key": key,
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "confirmed"
        created.append(response.json()["id"])
    cancelled_registration_id, remaining_registration_id = created

    db.expire_all()
    before_attendance = {
        row.id: (row.status, row.admission_order)
        for row in db.scalars(
            select(Registration).where(Registration.event_id == event.id)
        )
    }
    event_row = db.get(Event, event.id)
    event_capacity_state = (
        event_row.capacity, event_row.next_admission, event_row.interest_count,
    )
    chat_count = db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.event_id == event.id)
    ) or 0

    owner_token = token_for(owner)
    opened = _set_session(client, owner_token, event.id, True, 0, uuid4())
    assert opened.status_code == 200
    marked = _mark(
        client, owner_token, event.id, cancelled_registration_id, True, 1, uuid4(),
    )
    assert marked.status_code == 200

    db.expire_all()
    after_attendance = {
        row.id: (row.status, row.admission_order)
        for row in db.scalars(
            select(Registration).where(Registration.event_id == event.id)
        )
    }
    event_row = db.get(Event, event.id)
    assert after_attendance == before_attendance
    assert (
        event_row.capacity, event_row.next_admission, event_row.interest_count,
    ) == event_capacity_state
    assert db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.event_id == event.id)
    ) == chat_count

    before_cancel_state = client.get(
        f"/api/v1/events/{event.id}/attendance", headers=_auth(owner_token),
    ).json()
    history_before_cancel = client.get(
        f"/api/v1/events/{event.id}/attendance/history",
        headers=_auth(owner_token),
    ).json()
    assert before_cancel_state["confirmed_count"] == 2
    assert before_cancel_state["checked_in_count"] == 1
    assert len(history_before_cancel) == 2

    cancellation = client.delete(
        f"/api/v1/events/{event.id}/registrations/me",
        headers=_auth(token_for(withdrawing_attendee)),
    )
    assert cancellation.status_code == 200
    assert cancellation.json()["status"] == "cancelled"

    db.expire_all()
    after_cancel_state = client.get(
        f"/api/v1/events/{event.id}/attendance", headers=_auth(owner_token),
    ).json()
    history_after_cancel = client.get(
        f"/api/v1/events/{event.id}/attendance/history",
        headers=_auth(owner_token),
    ).json()
    assert after_cancel_state["confirmed_count"] == 1
    assert after_cancel_state["checked_in_count"] == 0
    assert [row["registration_id"] for row in after_cancel_state["attendees"]] == [
        remaining_registration_id,
    ]
    assert history_after_cancel == history_before_cancel

    retained_mark = db.scalar(
        select(AttendanceMark).where(
            AttendanceMark.registration_id == cancelled_registration_id,
        )
    )
    assert retained_mark is not None
    assert retained_mark.attended is True

    cancelled_retry = _mark(
        client, owner_token, event.id, cancelled_registration_id, True,
        after_cancel_state["version"], uuid4(),
    )
    assert cancelled_retry.status_code == 409
    assert cancelled_retry.json()["error"]["code"] == "attendance_registration_unavailable"
    assert client.get(
        f"/api/v1/events/{event.id}/attendance/history",
        headers=_auth(owner_token),
    ).json() == history_before_cancel

"""Independent Sprint 22 HTTP journeys; run only in the coordinator's serial DB slot."""
import json
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import now, uid
from app.domains.attendance.models import AttendanceAudit, AttendanceMark, AttendanceSession
from app.domains.eventsafety.models import (
    EventControl,
    EventReport,
    OrganizationSuspension,
    SafetyAudit,
)
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.main import create_app
from app.notifications import Notification


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _add_membership(db, org, user, role="member"):
    membership = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=True,
    )
    db.add(membership)
    db.commit()
    return membership


def _report(client, token, event_id, key, reason="safety"):
    return client.post(
        f"/api/v1/events/{event_id}/event-reports",
        headers=_auth(token),
        json={"reason": reason, "client_key": str(key)},
    )


def _event_action(client, token, event_id, action, version, key=None):
    return client.post(
        f"/api/v1/events/{event_id}/safety",
        headers=_auth(token),
        json={"action": action, "version": version, "client_key": str(key or uuid4())},
    )


def _suspend(client, token, org_id, version, days=7, key=None):
    return client.post(
        f"/api/v1/organizations/{org_id}/suspension",
        headers=_auth(token),
        json={
            "action": "suspend", "version": version, "days": days,
            "client_key": str(key or uuid4()),
        },
    )


def _register(client, token, event_id, key):
    return client.post(
        f"/api/v1/events/{event_id}/registrations",
        headers=_auth(token) | {"Idempotency-Key": key},
    )


def _png_bytes():
    stream = BytesIO()
    Image.new("RGB", (2, 2), (31, 83, 127)).save(stream, format="PNG")
    return stream.getvalue()


def _upload_and_publish_banner(client, event, token):
    draft = client.get(f"/api/v1/events/{event.id}/draft", headers=_auth(token))
    assert draft.status_code == 200
    draft_version = draft.json()["draft_version"]
    uploaded = client.post(
        f"/api/v1/events/{event.id}/banner",
        headers=_auth(token) | {
            "If-Match": f'"{draft_version}"',
            "Content-Type": "image/png",
        },
        content=_png_bytes(),
    )
    assert uploaded.status_code == 200, uploaded.json().get('error', {}).get('code')
    uploaded_version = uploaded.json()["draft_version"]
    published = client.post(
        f"/api/v1/events/{event.id}/publish",
        headers=_auth(token) | {
            "If-Match": f'"{uploaded_version}"',
        },
    )
    assert published.status_code == 200
    return uploaded.json()["media_url"]


def _notification_count(db, *, event_id=None, org_id=None, kind=None):
    query = select(func.count(Notification.id))
    if event_id is not None:
        query = query.where(Notification.event_id == event_id)
    if org_id is not None:
        query = query.where(Notification.org_id == org_id)
    if kind is not None:
        query = query.where(Notification.kind == kind)
    return db.scalar(query) or 0


def _seed_registration(db, event, user, status, order, owner):
    timestamp = now()
    review = status in {"pending", "reconfirmation_required"}
    registration = Registration(
        id=uid(), user_id=user.id, event_id=event.id, status=status,
        admission_order=order,
        confirmed_at=timestamp if status in {"confirmed", "reconfirmation_required"} else None,
        review_deadline=timestamp + timedelta(hours=1) if review else None,
        review_stage=0 if review else None,
        reviewer_id=owner.id if review else None,
        first_reviewer_id=owner.id if review else None,
        reconfirm_deadline=(timestamp + timedelta(hours=1)
                            if status == "reconfirmation_required" else None),
        reconfirm_revision=1 if status == "reconfirmation_required" else None,
    )
    db.add(registration)
    return registration


def test_report_receipts_escalate_by_distinct_reporters_without_auto_hiding(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, description="&<\"" * 700)
    reporter_a, reporter_b, reporter_c, reporter_d = (make_user() for _ in range(4))
    platform_admin = make_user(platform_admin=True)

    first_key = uuid4()
    first = _report(client, token_for(reporter_a), event.id, first_key)
    assert first.status_code == 201
    original = first.json()
    assert (original["stage"], original["status"]) == ("organization", "open")
    assert _report(client, token_for(reporter_a), event.id, first_key).json() == original

    queue = client.get(
        "/api/v1/moderation/event-reports", params={"org_id": org.id},
        headers=_auth(token_for(owner)),
    )
    assert queue.status_code == 200
    first_review = next(item for item in queue.json() if item["id"] == original["id"])
    assert first_review["evidence"]
    evidence = json.loads(first_review["evidence"])
    assert set(evidence) == {"title", "summary", "description", "venue_name", "venue_address"}
    assert len(first_review["evidence"]) <= 4096
    assert len(evidence["description"]) <= 2200
    assert reporter_a.email not in queue.text
    assert reporter_a.nickname not in queue.text
    state = client.get(
        f"/api/v1/events/{event.id}/safety", headers=_auth(token_for(owner)),
    )
    assert state.status_code == 200
    assert state.json()["org_hidden"] is False
    assert state.json()["platform_hidden"] is False

    dismissed = client.post(
        f"/api/v1/moderation/event-reports/{original['id']}/decision",
        headers=_auth(token_for(owner)),
        json={
            "action": "dismiss", "version": first_review["version"],
            "event_version": first_review["event_version"], "client_key": str(uuid4()),
        },
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert dismissed.json()["evidence"] is None
    assert _report(client, token_for(reporter_a), event.id, first_key).json() == original

    second = _report(client, token_for(reporter_b), event.id, uuid4())
    duplicate = _report(client, token_for(reporter_b), event.id, uuid4())
    third = _report(client, token_for(reporter_c), event.id, uuid4())
    fourth = _report(client, token_for(reporter_d), event.id, uuid4())
    assert [second.json()["stage"], duplicate.json()["stage"], third.json()["stage"]] == [
        "organization", "organization", "organization",
    ]
    assert duplicate.json()["id"] == second.json()["id"]
    assert (fourth.json()["stage"], fourth.json()["status"]) == ("platform", "escalated")

    platform_queue = client.get(
        "/api/v1/moderation/event-reports", headers=_auth(token_for(platform_admin)),
    )
    assert platform_queue.status_code == 200
    assert [item["id"] for item in platform_queue.json()] == [fourth.json()["id"]]
    assert db.scalar(select(func.count(EventReport.id)).where(
        EventReport.event_id == event.id,
        EventReport.reporter_id == reporter_b.id,
    )) == 1
    assert db.scalar(select(func.count(SafetyAudit.id)).where(
        SafetyAudit.event_id == event.id,
        SafetyAudit.actor_id == reporter_a.id,
        SafetyAudit.action == "report",
    )) == 1


def test_organization_and_platform_hide_channels_are_separate_and_terminal(
    client, db, make_user, make_org, make_event, token_for, monkeypatch, tmp_path,
):
    monkeypatch.setattr(get_settings(), "media_root", tmp_path)
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org)
    platform_admin = make_user(platform_admin=True)

    forbidden_remove = _event_action(client, token_for(owner), event.id, "remove", 0)
    forbidden_suspend = _suspend(client, token_for(owner), org.id, 0, days=1)
    assert forbidden_remove.status_code == 403
    assert forbidden_suspend.status_code == 403
    assert db.get(OrganizationSuspension, org.id) is None

    org_hide = _event_action(client, token_for(owner), event.id, "hide", 0)
    assert org_hide.status_code == 200
    assert (org_hide.json()["org_hidden"], org_hide.json()["platform_hidden"]) == (True, False)
    assert org_hide.json()["registration_available"] is False

    platform_hide = _event_action(
        client, token_for(platform_admin), event.id, "hide", org_hide.json()["version"],
    )
    assert platform_hide.status_code == 200
    assert (platform_hide.json()["org_hidden"], platform_hide.json()["platform_hidden"]) == (True, True)

    org_restore = _event_action(
        client, token_for(owner), event.id, "restore", platform_hide.json()["version"],
    )
    assert org_restore.status_code == 200
    assert (org_restore.json()["org_hidden"], org_restore.json()["platform_hidden"]) == (False, True)
    platform_restore = _event_action(
        client, token_for(platform_admin), event.id, "restore", org_restore.json()["version"],
    )
    assert platform_restore.status_code == 200
    assert (platform_restore.json()["org_hidden"], platform_restore.json()["platform_hidden"]) == (False, False)

    removed = _event_action(
        client, token_for(platform_admin), event.id, "remove", platform_restore.json()["version"],
    )
    assert removed.status_code == 200
    assert removed.json()["removed"] is True
    no_resurrection = _event_action(
        client, token_for(platform_admin), event.id, "restore", removed.json()["version"],
    )
    assert no_resurrection.status_code == 409
    final = client.get(
        f"/api/v1/events/{event.id}/safety", headers=_auth(token_for(platform_admin)),
    )
    assert final.status_code == 200
    assert final.json()["removed"] is True
    assert final.json()["org_hidden"] is False
    assert final.json()["platform_hidden"] is False

    draft = make_event(org=org, status="draft", published_at=None)
    draft_path = f"/api/v1/events/{draft.id}/draft"
    before = client.get(draft_path, headers=_auth(token_for(owner)))
    assert before.status_code == 200
    draft_safety = client.get(
        f"/api/v1/events/{draft.id}/safety", headers=_auth(token_for(platform_admin)),
    )
    assert draft_safety.status_code == 200
    assert draft_safety.json()["can_remove"] is True
    draft_removal = _event_action(
        client, token_for(platform_admin), draft.id, "remove", draft_safety.json()["version"],
    )
    assert draft_removal.status_code == 200
    assert draft_removal.json()["removed"] is True

    # Read the current draft version and use that exact If-Match on every write.
    after = client.get(draft_path, headers=_auth(token_for(owner)))
    assert after.status_code == 200
    assert after.json()["draft_version"] == before.json()["draft_version"]
    current_draft_version = after.json()["draft_version"]
    if_match = f'"{current_draft_version}"'
    owner_headers = _auth(token_for(owner))
    patch = client.patch(
        draft_path,
        headers=owner_headers | {"If-Match": if_match},
        json={"title": "Must remain unchanged after removal"},
    )
    banner = client.post(
        f"/api/v1/events/{draft.id}/banner",
        headers=owner_headers | {"If-Match": if_match, "Content-Type": "image/png"},
        content=_png_bytes(),
    )
    publish = client.post(
        f"/api/v1/events/{draft.id}/publish",
        headers=owner_headers | {"If-Match": if_match},
    )
    for response in (patch, banner, publish):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "event_terminal"


def test_suspension_expires_at_boundary_once_across_app_recreation(
    client, db, make_user, make_org, make_event, token_for, monkeypatch,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org)
    platform_admin = make_user(platform_admin=True)
    platform_token = token_for(platform_admin)
    owner_token = token_for(owner)

    suspended = _suspend(client, platform_token, org.id, 0, days=1)
    assert suspended.status_code == 200
    assert suspended.json()["is_suspended"] is True
    assert suspended.json()["version"] == 1

    boundary = now()
    suspension = db.get(OrganizationSuspension, org.id)
    suspension.suspended_until = boundary
    db.commit()
    notices_before = _notification_count(db, org_id=org.id, kind="organization_safety")

    from app.domains.eventsafety import service as safety_service
    monkeypatch.setattr(safety_service, "now", lambda: boundary)
    path = f"/api/v1/organizations/{org.id}/suspension"
    exact_boundary = client.get(path, headers=_auth(owner_token))
    assert exact_boundary.status_code == 200
    assert exact_boundary.json()["is_suspended"] is False
    assert exact_boundary.json()["version"] == 2
    assert exact_boundary.json()["suspended_until"] is None

    with TestClient(create_app()) as restarted_app:
        repeated = restarted_app.get(path, headers=_auth(owner_token))
        discovery = restarted_app.get("/api/v1/events")
        detail = restarted_app.get(f"/api/v1/events/{event.id}")
    assert repeated.status_code == 200
    assert repeated.json() == exact_boundary.json()
    assert discovery.status_code == 200
    assert detail.status_code == 200

    db.expire_all()
    expiries = list(db.scalars(select(SafetyAudit).where(
        SafetyAudit.org_id == org.id, SafetyAudit.scope == "organization",
        SafetyAudit.action == "expire",
    )))
    assert len(expiries) == 1
    assert expiries[0].actor_id is None
    assert _notification_count(db, org_id=org.id, kind="organization_safety") == notices_before + 1


def test_hidden_and_suspended_events_block_new_intake_but_preserve_existing_work(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    owner_token = token_for(owner)
    platform_admin = make_user(platform_admin=True)
    platform_token = token_for(platform_admin)

    instant = make_event(org=org, capacity=1)
    confirmed, first_waiter, second_waiter, outsider = (make_user() for _ in range(4))
    first = _register(client, token_for(confirmed), instant.id, "s22-confirmed-001")
    second = _register(client, token_for(first_waiter), instant.id, "s22-waitlist-001")
    third = _register(client, token_for(second_waiter), instant.id, "s22-waitlist-002")
    assert [first.json()["status"], second.json()["status"], third.json()["status"]] == [
        "confirmed", "waitlisted", "waitlisted",
    ]
    existing_chat = client.post(
        f"/api/v1/events/{instant.id}/chat/messages",
        headers=_auth(token_for(confirmed)),
        json={"body": "Existing participant chat survives restrictions.", "client_key": str(uuid4())},
    )
    assert existing_chat.status_code == 200

    approval = make_event(org=org, capacity=1, registration_mode="approval", review_window_minutes=60)
    applicant = make_user()
    pending = _register(client, token_for(applicant), approval.id, "s22-pending-001")
    assert pending.status_code == 201
    assert pending.json()["status"] == "pending"

    hidden = _event_action(client, owner_token, instant.id, "hide", 0)
    assert hidden.status_code == 200
    suspended = _suspend(client, platform_token, org.id, 0, days=2)
    assert suspended.status_code == 200

    for restricted_event in (instant, approval):
        denied = _register(
            client, token_for(outsider), restricted_event.id,
            f"s22-bypass-{restricted_event.id}",
        )
        assert denied.status_code == 409
        assert denied.json()["error"]["code"] == "event_registration_unavailable"
        assert client.get(f"/api/v1/events/{restricted_event.id}").status_code == 404

    attendee_detail = client.get(
        f"/api/v1/events/{instant.id}", headers=_auth(token_for(confirmed)),
    )
    assert attendee_detail.status_code == 200
    chat = client.get(
        f"/api/v1/events/{instant.id}/chat", headers=_auth(token_for(confirmed)),
    )
    assert chat.status_code == 200
    assert any(item["id"] == existing_chat.json()["id"] for item in chat.json()["items"])
    continued_chat = client.post(
        f"/api/v1/events/{instant.id}/chat/messages",
        headers=_auth(token_for(confirmed)),
        json={"body": "A new message after hide and suspension.", "client_key": str(uuid4())},
    )
    assert continued_chat.status_code == 200

    review_queue = client.get(
        f"/api/v1/events/{approval.id}/registration-review", headers=_auth(owner_token),
    )
    assert review_queue.status_code == 200
    assert pending.json()["id"] in {item["registration"]["id"] for item in review_queue.json()}
    approved = client.post(
        f"/api/v1/events/{approval.id}/registrations/{pending.json()['id']}/decision",
        headers=_auth(owner_token), json={"decision": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "confirmed"

    withdrawal = client.delete(
        f"/api/v1/events/{instant.id}/registrations/me", headers=_auth(token_for(confirmed)),
    )
    assert withdrawal.status_code == 200
    promoted = client.get("/api/v1/me/registrations", headers=_auth(token_for(first_waiter)))
    still_waiting = client.get("/api/v1/me/registrations", headers=_auth(token_for(second_waiter)))
    assert promoted.status_code == still_waiting.status_code == 200
    assert promoted.json()[0]["status"] == "confirmed"
    assert still_waiting.json()[0]["status"] == "waitlisted"

    replay = _register(client, token_for(confirmed), instant.id, "s22-confirmed-001")
    assert replay.status_code == first.status_code
    assert replay.json() == first.json()
    db.expire_all()
    assert db.scalar(select(func.count(Registration.id)).where(
        Registration.event_id.in_((instant.id, approval.id)),
        Registration.user_id == outsider.id,
    )) == 0


@pytest.mark.parametrize("terminal_action", ["remove", "cancel"])
def test_terminal_action_cancels_participation_and_preserves_attendance_history(
    client, db, make_user, make_org, make_event, token_for, terminal_action,
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(get_settings(), "media_root", tmp_path)
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, capacity=4, status="draft", published_at=None)
    owner_token = token_for(owner)
    banner_url = _upload_and_publish_banner(client, event, owner_token)
    assert client.get(banner_url).status_code == 200
    participants = [make_user() for _ in range(4)]
    statuses = ["confirmed", "waitlisted", "pending", "reconfirmation_required"]
    registrations = [
        _seed_registration(db, event, user, status, index, owner)
        for index, (user, status) in enumerate(zip(participants, statuses), start=1)
    ]
    receipts = [
        RegistrationReceipt(
            id=uid(), user_id=user.id, event_id=event.id,
            idempotency_key=f"s22-pending-{terminal_action}-{index}", event_order=index,
        )
        for index, user in enumerate(participants, start=1)
    ]
    completed_result = {
        "id": registrations[0].id,
        "event_id": event.id,
        "status": "confirmed",
        "waitlist_position": None,
        "waitlist_message": None,
        "admission_order": registrations[0].admission_order,
        "review_deadline": None,
        "review_stage": None,
        "reviewer_id": None,
        "first_reviewer_id": None,
        "timeout_count": 0,
        "from_waitlist": False,
        "persona_shared": False,
        "reconfirm_deadline": None,
        "reconfirm_revision": None,
    }
    completed_receipt = RegistrationReceipt(
        id=uid(), user_id=participants[0].id, event_id=event.id,
        idempotency_key=f"s22-completed-{terminal_action}", event_order=99,
        result=completed_result,
        http_status=201, processed_at=now(),
    )
    completed_processed_at = completed_receipt.processed_at
    db.add_all([*receipts, completed_receipt])
    db.commit()

    opened = client.post(
        f"/api/v1/events/{event.id}/attendance/session",
        headers=_auth(owner_token),
        json={"is_open": True, "version": 0, "client_key": str(uuid4())},
    )
    assert opened.status_code == 200
    marked = client.put(
        f"/api/v1/events/{event.id}/attendance/registrations/{registrations[0].id}",
        headers=_auth(owner_token),
        json={"attended": True, "version": opened.json()["version"], "client_key": str(uuid4())},
    )
    assert marked.status_code == 200
    db.expire_all()
    session_before = db.get(AttendanceSession, event.id)
    attendance_state = (session_before.is_open, session_before.version)
    mark_before = db.get(AttendanceMark, registrations[0].id).attended
    audit_count_before = db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.event_id == event.id,
    ))

    terminal_actor = make_user(platform_admin=True) if terminal_action == "remove" else owner
    token = token_for(terminal_actor)
    action_key = uuid4()
    action = _event_action(client, token, event.id, terminal_action, 0, action_key)
    assert action.status_code == 200
    expected_flag = "removed" if terminal_action == "remove" else "cancelled"
    assert action.json()[expected_flag] is True
    assert client.get(banner_url).status_code == 404
    # Terminal banners remain available only through the existing private staff path.
    assert client.get(banner_url, headers=_auth(owner_token)).status_code == 200
    notice_count = _notification_count(
        db, event_id=event.id, kind="event_safety_cancelled",
    )
    assert notice_count == len(set([owner.id, *(user.id for user in participants)]))

    retry = _event_action(
        client, token, event.id, terminal_action, 0,
        key=action_key,
    )
    assert retry.status_code == 200
    assert retry.json() == action.json()

    sealed_key = f"s22-pending-{terminal_action}-1"
    sealed_retry = _register(client, token_for(participants[0]), event.id, sealed_key)
    assert sealed_retry.status_code == 409
    assert sealed_retry.json()["error"]["code"] == "event_terminal"
    completed_key = f"s22-completed-{terminal_action}"
    completed_retry = _register(
        client, token_for(participants[0]), event.id, completed_key,
    )
    assert completed_retry.status_code == 201
    assert completed_retry.json() == completed_result

    db.expire_all()
    current = list(db.scalars(select(Registration).where(Registration.event_id == event.id)))
    assert len(current) == len(statuses)
    assert {row.status for row in current} == {"cancelled"}
    assert all(
        row.review_deadline is None and row.review_stage is None
        and row.reviewer_id is None and row.first_reviewer_id is None
        and row.reconfirm_deadline is None and row.reconfirm_revision is None
        for row in current
    )
    sealed = list(db.scalars(select(RegistrationReceipt).where(
        RegistrationReceipt.id.in_([receipt.id for receipt in receipts]),
    )))
    assert all(row.http_status == 409 and row.result["error"]["code"] == "event_terminal"
               and row.processed_at is not None for row in sealed)
    preserved_receipt = db.get(RegistrationReceipt, completed_receipt.id)
    assert preserved_receipt.result == completed_result
    assert preserved_receipt.http_status == 201
    assert preserved_receipt.processed_at == completed_processed_at
    assert db.scalar(select(func.count(RegistrationReceipt.id)).where(
        RegistrationReceipt.user_id == participants[0].id,
        RegistrationReceipt.event_id == event.id,
        RegistrationReceipt.idempotency_key == sealed_key,
    )) == 1
    current_session = db.get(AttendanceSession, event.id)
    assert (current_session.is_open, current_session.version) == attendance_state
    assert db.get(AttendanceMark, registrations[0].id).attended is True
    assert mark_before is True
    assert db.scalar(select(func.count(AttendanceAudit.id)).where(
        AttendanceAudit.event_id == event.id,
    )) == audit_count_before
    assert _notification_count(db, event_id=event.id, kind="event_safety_cancelled") == notice_count
    assert client.get(f"/api/v1/events/{event.id}").status_code == 404


def test_stale_safety_versions_and_replays_recheck_current_authority(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    organization_admin = make_user()
    admin_membership = _add_membership(db, org, organization_admin, role="admin")
    event = make_event(org=org)
    key = uuid4()
    original = _event_action(client, token_for(organization_admin), event.id, "hide", 0, key)
    assert original.status_code == 200
    replay = _event_action(client, token_for(organization_admin), event.id, "hide", 0, key)
    assert replay.status_code == 200
    assert replay.json() == original.json()

    stale = _event_action(client, token_for(organization_admin), event.id, "restore", 0)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "event_safety_version_conflict"
    reused_key = _event_action(
        client, token_for(organization_admin), event.id, "restore", 1, key,
    )
    assert reused_key.status_code == 409
    assert reused_key.json()["error"]["code"] == "safety_idempotency_conflict"

    platform_admin = make_user(platform_admin=True)
    platform_key = uuid4()
    platform_hide = _event_action(
        client, token_for(platform_admin), event.id, "hide", 1, platform_key,
    )
    assert platform_hide.status_code == 200
    platform_admin.platform_admin = False
    admin_membership.role = "member"
    db.commit()

    revoked_org_replay = _event_action(
        client, token_for(organization_admin), event.id, "hide", 0, key,
    )
    revoked_platform_replay = _event_action(
        client, token_for(platform_admin), event.id, "hide", 1, platform_key,
    )
    assert revoked_org_replay.status_code == 403
    assert revoked_platform_replay.status_code == 403
    db.expire_all()
    control = db.get(EventControl, event.id)
    assert (control.org_hidden, control.platform_hidden, control.version) == (True, True, 2)
    assert db.scalar(select(func.count(SafetyAudit.id)).where(
        SafetyAudit.event_id == event.id, SafetyAudit.scope == "event",
        SafetyAudit.action == "hide",
    )) == 2

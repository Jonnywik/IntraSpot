import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import now, uid
from app.db.session import engine
from app.domains.eventsafety import service
from app.domains.eventsafety.models import (
    EventControl,
    EventReport,
    OrganizationSuspension,
    SafetyAudit,
)
from app.domains.organizations.models import OrgMembership
from app.notifications import Notification


def auth(user, token_for, **claims):
    return {"Authorization": f"Bearer {token_for(user, **claims)}"}


def add_membership(db, org, user, role):
    membership = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=True
    )
    db.add(membership)
    db.commit()
    return membership


def submit_report(client, event, user, token_for, *, key=None, reason="safety"):
    return client.post(
        f"/api/v1/events/{event.id}/event-reports",
        json={"reason": reason, "client_key": str(key or uuid4())},
        headers=auth(user, token_for),
    )


def decide_report(
    client,
    report_id,
    actor,
    token_for,
    *,
    action,
    version=1,
    event_version=0,
    key=None,
):
    return client.post(
        f"/api/v1/moderation/event-reports/{report_id}/decision",
        json={
            "action": action,
            "version": version,
            "event_version": event_version,
            "client_key": str(key or uuid4()),
        },
        headers=auth(actor, token_for),
    )


def test_models_match_frozen_constraints_and_indexes():
    assert EventControl.__tablename__ == "event_controls"
    assert "ck_event_controls_version" in {
        constraint.name for constraint in EventControl.__table__.constraints
    }
    assert OrganizationSuspension.__tablename__ == "organization_suspensions"
    assert "ck_organization_suspensions_version" in {
        constraint.name for constraint in OrganizationSuspension.__table__.constraints
    }
    assert EventReport.__tablename__ == "event_reports"
    report_constraints = {item.name for item in EventReport.__table__.constraints}
    assert {
        "ck_event_reports_reason",
        "ck_event_reports_stage",
        "ck_event_reports_status",
        "ck_event_reports_version",
    } <= report_constraints
    report_indexes = {item.name: item for item in EventReport.__table__.indexes}
    assert "uq_event_reports_active_reporter" in report_indexes
    assert "ix_event_reports_event_created" in report_indexes
    assert "status IN ('open','escalated')" in str(
        report_indexes["uq_event_reports_active_reporter"].dialect_options[
            "postgresql"
        ]["where"]
    )
    assert str(EventReport.__table__.c.version.server_default.arg) == "1"
    assert SafetyAudit.__tablename__ == "safety_audits"
    audit_constraints = {item.name for item in SafetyAudit.__table__.constraints}
    assert {
        "uq_safety_audits_actor_key",
        "ck_safety_audits_scope",
        "ck_safety_audits_action",
        "ck_safety_audits_version",
    } <= audit_constraints
    assert "ix_safety_audits_org_created" in {
        item.name for item in SafetyAudit.__table__.indexes
    }


def test_report_accepts_json_uuid_string_and_returns_frozen_receipt(
    client, make_user, make_org, make_event, token_for
):
    reporter = make_user()
    event = make_event(org=make_org())
    response = submit_report(client, event, reporter, token_for, key=uuid4())

    assert response.status_code == 201
    assert set(response.json()) == {
        "id", "event_id", "org_id", "status", "stage", "version", "deadline"
    }
    assert response.json()["event_id"] == event.id
    assert response.json()["status"] == "open"
    assert response.json()["stage"] == "organization"
    assert response.json()["version"] == 1


def test_report_and_decision_inputs_reject_extra_fields_and_boolean_versions(
    client, make_user, make_org, make_event, token_for
):
    reporter = make_user()
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org)
    report = submit_report(client, event, reporter, token_for).json()

    extra = client.post(
        f"/api/v1/events/{event.id}/event-reports",
        json={"reason": "safety", "client_key": str(uuid4()), "message": "private"},
        headers=auth(reporter, token_for),
    )
    boolean_version = decide_report(
        client,
        report["id"],
        owner,
        token_for,
        action="dismiss",
        version=True,
    )
    assert extra.status_code == 422
    assert boolean_version.status_code == 422


def test_active_duplicate_and_exact_retry_return_original_receipt_once(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    reporter = make_user()
    event = make_event(org=make_org(owner=owner))
    key = uuid4()

    first = submit_report(client, event, reporter, token_for, key=key)
    exact_retry = submit_report(client, event, reporter, token_for, key=key)
    active_duplicate = submit_report(client, event, reporter, token_for)

    assert first.status_code == exact_retry.status_code == active_duplicate.status_code == 201
    assert first.json() == exact_retry.json()
    assert first.json()["id"] == active_duplicate.json()["id"]
    assert db.scalar(select(func.count(EventReport.id))) == 1
    assert db.scalar(
        select(func.count(SafetyAudit.id)).where(
            SafetyAudit.report_id == first.json()["id"], SafetyAudit.action == "report"
        )
    ) == 2
    assert db.scalar(
        select(func.count(Notification.id)).where(
            Notification.kind == "event_safety_report"
        )
    ) == 1


def test_reusing_a_request_key_with_different_payload_conflicts(
    client, make_user, make_org, make_event, token_for
):
    reporter = make_user()
    event = make_event(org=make_org())
    key = uuid4()
    first = submit_report(client, event, reporter, token_for, key=key, reason="safety")
    conflict = submit_report(
        client, event, reporter, token_for, key=key, reason="deception"
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "safety_idempotency_conflict"


def test_reporting_requires_eligible_signed_in_reader(
    client, db, make_user, make_org, make_event, token_for
):
    event = make_event(org=make_org())
    guest = client.post(
        f"/api/v1/events/{event.id}/event-reports",
        json={"reason": "safety", "client_key": str(uuid4())},
    )
    ineligible = make_user(email="fictional@example.test", email_verified=True)
    denied = submit_report(client, event, ineligible, token_for)

    db.add(EventControl(event_id=event.id, org_hidden=True))
    db.commit()
    outside_reader = make_user()
    hidden = submit_report(client, event, outside_reader, token_for)

    assert guest.status_code == 401
    assert denied.status_code == 403
    assert hidden.status_code == 404


def test_moderation_snapshot_is_bounded_public_text_and_org_scoped(
    client, make_user, make_org, make_event, token_for
):
    owner = make_user()
    reporter = make_user()
    org = make_org(owner=owner)
    quote_slash = chr(34) + chr(92)
    event = make_event(
        org=org,
        title="<b>Fictional gathering</b>" + quote_slash * 80,
        summary=quote_slash * 190,
        description="<script>private marker</script>" + quote_slash * 900,
        venue_name=quote_slash * 90,
        venue_address=quote_slash * 230,
    )
    receipt = submit_report(client, event, reporter, token_for).json()

    queue = client.get(
        "/api/v1/moderation/event-reports",
        params={"org_id": org.id},
        headers=auth(owner, token_for),
    )
    assert queue.status_code == 200
    review = queue.json()[0]
    assert set(review) == {
        "id", "event_id", "org_id", "status", "stage", "version", "deadline",
        "reason", "evidence", "reporter_id", "created_at", "event_version", "decisions",
    }
    assert review["id"] == receipt["id"]
    snapshot = json.loads(review["evidence"])
    assert set(snapshot) == {"title", "summary", "description", "venue_name", "venue_address"}
    assert snapshot["title"].startswith("<b>Fictional gathering</b>")
    assert snapshot["description"].startswith("<script>private marker</script>")
    assert len(review["evidence"].encode("utf-8")) <= 4096
    assert reporter.email not in review["evidence"]
    assert reporter.nickname not in review["evidence"]


def test_org_review_uses_current_staff_role_and_limits_actions(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    moderator = make_user()
    reporter = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org)
    membership = add_membership(db, org, moderator, "moderator")
    report = submit_report(client, event, reporter, token_for).json()

    membership.role = "member"
    db.commit()
    stale_role = client.get(
        "/api/v1/moderation/event-reports",
        params={"org_id": org.id},
        headers=auth(moderator, token_for),
    )
    membership.role = "moderator"
    db.commit()
    forbidden = decide_report(
        client,
        report["id"],
        moderator,
        token_for,
        action="remove",
    )
    dismissed = decide_report(
        client,
        report["id"],
        moderator,
        token_for,
        action="dismiss",
    )

    assert stale_role.status_code == 403
    assert forbidden.status_code == 403
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"


def test_three_distinct_post_decision_reporters_escalate_without_auto_hiding(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    reporters = [make_user() for _ in range(4)]
    event = make_event(org=make_org(owner=owner))
    first = submit_report(client, event, reporters[0], token_for).json()
    dismissed = decide_report(
        client, first["id"], owner, token_for, action="dismiss", event_version=0
    )
    second = submit_report(client, event, reporters[1], token_for).json()
    third = submit_report(client, event, reporters[2], token_for).json()
    fourth = submit_report(client, event, reporters[3], token_for).json()

    assert dismissed.status_code == 200
    assert second["stage"] == third["stage"] == "organization"
    assert fourth["stage"] == "platform"
    assert fourth["status"] == "escalated"
    fourth_row = db.get(EventReport, fourth["id"])
    assert fourth_row.deadline - fourth_row.created_at == timedelta(days=14)
    assert db.get(EventControl, event.id).org_hidden is False
    assert db.get(EventControl, event.id).platform_hidden is False

    org_reviewed_at = db.get(EventControl, event.id).org_reviewed_at
    platform = make_user(platform_admin=True)
    closed = decide_report(
        client, fourth["id"], platform, token_for, action="dismiss", event_version=1
    )
    repeated_report = submit_report(client, event, reporters[3], token_for).json()

    assert closed.status_code == 200
    assert db.get(EventControl, event.id).org_reviewed_at == org_reviewed_at
    assert repeated_report["stage"] == "platform"
    assert repeated_report["status"] == "escalated"


def test_refreshed_report_token_tracks_material_and_control_versions(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    reporter = make_user()
    event = make_event(org=make_org(owner=owner))
    report = submit_report(client, event, reporter, token_for).json()
    queue_url = "/api/v1/moderation/event-reports"
    params = {"org_id": event.org_id}
    headers = auth(owner, token_for)
    initial = client.get(queue_url, params=params, headers=headers).json()[0]

    hide = client.post(
        f"/api/v1/events/{event.id}/safety",
        json={"action": "hide", "version": 0, "client_key": str(uuid4())},
        headers=headers,
    )
    event.material_revision = 1
    db.commit()
    restore = client.post(
        f"/api/v1/events/{event.id}/safety",
        json={"action": "restore", "version": 1, "client_key": str(uuid4())},
        headers=headers,
    )
    stale = decide_report(
        client,
        report["id"],
        owner,
        token_for,
        action="dismiss",
        version=initial["version"],
        event_version=initial["event_version"],
    )
    refreshed = client.get(queue_url, params=params, headers=headers).json()[0]
    accepted = decide_report(
        client,
        report["id"],
        owner,
        token_for,
        action="dismiss",
        version=refreshed["version"],
        event_version=refreshed["event_version"],
    )

    assert hide.json()["version"] == 1
    assert restore.json()["version"] == 2
    assert initial["event_version"] == 0
    assert stale.status_code == 409
    assert refreshed["event_version"] == 3
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "dismissed"


def test_org_and_platform_hide_channels_restore_independently(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    moderator = make_user()
    platform = make_user(platform_admin=True)
    org = make_org(owner=owner)
    event = make_event(org=org)
    add_membership(db, org, moderator, "moderator")
    url = f"/api/v1/events/{event.id}/safety"

    def hide_at_version_zero():
        return client.post(
            url,
            json={"action": "hide", "version": 0, "client_key": str(uuid4())},
            headers=auth(moderator, token_for),
        )

    def restore_at_version_zero():
        return client.post(
            url,
            json={"action": "restore", "version": 0, "client_key": str(uuid4())},
            headers=auth(moderator, token_for),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        hide_future = pool.submit(hide_at_version_zero)
        restore_race_future = pool.submit(restore_at_version_zero)
        org_hide = hide_future.result()
        restore_race = restore_race_future.result()
    platform_hide = client.post(
        url,
        json={"action": "hide", "version": 1, "client_key": str(uuid4())},
        headers=auth(platform, token_for),
    )
    org_restore = client.post(
        url,
        json={"action": "restore", "version": 2, "client_key": str(uuid4())},
        headers=auth(moderator, token_for),
    )
    platform_restore = client.post(
        url,
        json={"action": "restore", "version": 3, "client_key": str(uuid4())},
        headers=auth(platform, token_for),
    )

    assert org_hide.status_code == 200
    assert restore_race.status_code == 409
    assert org_hide.json()["org_hidden"] is True
    assert org_hide.json()["registration_available"] is False
    assert platform_hide.json()["platform_hidden"] is True
    assert org_restore.json()["org_hidden"] is False
    assert org_restore.json()["platform_hidden"] is True
    assert org_restore.json()["registration_available"] is False
    assert platform_restore.json()["platform_hidden"] is False
    assert platform_restore.json()["registration_available"] is True


def test_cancel_requires_owner_or_admin_and_sets_terminal_before_hook(
    client, db, make_user, make_org, make_event, token_for, monkeypatch
):
    owner = make_user()
    moderator = make_user()
    platform = make_user(platform_admin=True)
    org = make_org(owner=owner)
    event = make_event(org=org)
    add_membership(db, org, moderator, "moderator")
    observed = []

    def hook(session, locked_event, action_id):
        control = session.get(EventControl, locked_event.id)
        observed.append((control.cancelled, action_id))

    from app.domains.registrations import service as registrations_service

    monkeypatch.setattr(
        registrations_service, "cancel_event_participation_locked", hook
    )
    url = f"/api/v1/events/{event.id}/safety"
    body = {"action": "cancel", "version": 0, "client_key": str(uuid4())}
    moderator_denied = client.post(url, json=body, headers=auth(moderator, token_for))
    platform_denied = client.post(
        url,
        json={"action": "cancel", "version": 0, "client_key": str(uuid4())},
        headers=auth(platform, token_for),
    )
    cancelled = client.post(url, json=body, headers=auth(owner, token_for))

    assert moderator_denied.status_code == 403
    assert platform_denied.status_code == 403
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"] is True
    assert observed == [(True, observed[0][1])]


def test_platform_remove_from_report_calls_shared_hook_after_terminal_flag(
    client, db, make_user, make_org, make_event, token_for, monkeypatch
):
    owner = make_user()
    platform = make_user(platform_admin=True)
    reporters = [make_user() for _ in range(3)]
    org = make_org(owner=owner)
    event = make_event(org=org)
    db.add(EventControl(event_id=event.id, org_reviewed_at=now() - timedelta(hours=1)))
    db.commit()
    reports = [submit_report(client, event, user, token_for).json() for user in reporters]
    escalated = reports[-1]
    assert escalated["stage"] == "platform"
    observed = []

    def hook(session, locked_event, action_id):
        control = session.get(EventControl, locked_event.id)
        observed.append((control.removed, action_id))

    from app.domains.registrations import service as registrations_service

    monkeypatch.setattr(
        registrations_service, "cancel_event_participation_locked", hook
    )
    response = decide_report(
        client,
        escalated["id"],
        platform,
        token_for,
        action="remove",
        event_version=0,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "removed"
    assert db.get(EventControl, event.id).removed is True
    assert len(observed) == 1 and observed[0][0] is True


def test_platform_metadata_claim_does_not_grant_safety_authority(
    client, make_user, make_org, make_event, token_for
):
    owner = make_user()
    ordinary_user = make_user()
    event = make_event(org=make_org(owner=owner))
    response = client.post(
        f"/api/v1/events/{event.id}/safety",
        json={"action": "remove", "version": 0, "client_key": str(uuid4())},
        headers=auth(ordinary_user, token_for, platform_admin=True),
    )

    assert response.status_code == 403


def test_suspension_reads_allow_staff_but_only_platform_can_change_it(
    client, db, make_user, make_org, token_for, monkeypatch
):
    fixed_time = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: fixed_time)
    owner = make_user()
    moderator = make_user()
    platform = make_user(platform_admin=True)
    org = make_org(owner=owner)
    add_membership(db, org, moderator, "moderator")
    url = f"/api/v1/organizations/{org.id}/suspension"

    staff_read = client.get(url, headers=auth(moderator, token_for))
    staff_write = client.post(
        url,
        json={"action": "suspend", "version": 0, "days": 1, "client_key": str(uuid4())},
        headers=auth(moderator, token_for),
    )
    default_duration = client.post(
        url,
        json={"action": "suspend", "version": 0, "client_key": str(uuid4())},
        headers=auth(platform, token_for),
    )

    assert staff_read.status_code == 200
    assert staff_read.json()["can_manage"] is False
    assert staff_write.status_code == 403
    assert default_duration.status_code == 200
    assert datetime.fromisoformat(default_duration.json()["suspended_until"]) == (
        fixed_time + timedelta(days=7)
    )
    assert default_duration.json()["can_manage"] is True


def test_suspension_input_is_strict_about_days_version_and_resume(
    client, make_user, make_org, token_for
):
    platform = make_user(platform_admin=True)
    org = make_org()
    url = f"/api/v1/organizations/{org.id}/suspension"
    invalid = [
        {"action": "suspend", "version": True, "days": 1, "client_key": str(uuid4())},
        {"action": "suspend", "version": 0, "days": True, "client_key": str(uuid4())},
        {"action": "suspend", "version": 0, "days": 0, "client_key": str(uuid4())},
        {"action": "suspend", "version": 0, "days": 31, "client_key": str(uuid4())},
        {"action": "resume", "version": 0, "days": 1, "client_key": str(uuid4())},
        {"action": "suspend", "version": 0, "client_key": str(uuid4()), "note": "x"},
    ]

    responses = [
        client.post(url, json=body, headers=auth(platform, token_for))
        for body in invalid
    ]
    assert all(response.status_code == 422 for response in responses)


def test_suspension_expiry_is_exact_durable_and_idempotent(
    client, db, make_user, make_org, token_for, monkeypatch
):
    platform = make_user(platform_admin=True)
    owner = make_user()
    org = make_org(owner=owner)
    url = f"/api/v1/organizations/{org.id}/suspension"
    start = client.post(
        url,
        json={"action": "suspend", "version": 0, "days": 1, "client_key": str(uuid4())},
        headers=auth(platform, token_for),
    )
    deadline = datetime.fromisoformat(start.json()["suspended_until"])
    monkeypatch.setattr(service, "now", lambda: deadline)

    def expire_in_separate_session():
        with Session(engine(), expire_on_commit=False) as session:
            changed = service.sweep_expired_suspensions(
                session, str(org.id), deadline
            )
            session.commit()
            return changed

    def manual_resume_at_expiry():
        return client.post(
            url,
            json={"action": "resume", "version": 1, "client_key": str(uuid4())},
            headers=auth(platform, token_for),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        sweep_future = pool.submit(expire_in_separate_session)
        resume_future = pool.submit(manual_resume_at_expiry)
        first_sweep = sweep_future.result()
        resume = resume_future.result()
    db.expire_all()
    retry_sweep = service.sweep_expired_suspensions(db, str(org.id), deadline)
    state = db.get(OrganizationSuspension, org.id)
    expiry_audits = list(
        db.scalars(
            select(SafetyAudit).where(
                SafetyAudit.org_id == org.id,
                SafetyAudit.scope == "organization",
                SafetyAudit.action == "expire",
            )
        )
    )
    resume_audits = list(
        db.scalars(
            select(SafetyAudit).where(
                SafetyAudit.org_id == org.id,
                SafetyAudit.scope == "organization",
                SafetyAudit.action == "resume",
            )
        )
    )
    expiry_notices = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.org_id == org.id,
            Notification.kind == "organization_safety",
            Notification.dedupe_key.like(
                f"event_safety:organization:{org.id}:version:{state.version}:%"
            ),
        )
    )
    read = client.get(url, headers=auth(platform, token_for))

    assert start.status_code == 200
    assert first_sweep in {0, 1}
    assert resume.status_code == 200
    assert resume.json()["version"] == 2
    assert retry_sweep == 0
    assert state.suspended_until is None and state.version == 2
    assert len(expiry_audits) == 1
    assert expiry_audits[0].actor_id is None
    assert expiry_audits[0].created_at == deadline
    assert len(resume_audits) == 1
    assert resume.json()["is_suspended"] is False
    assert expiry_notices == 1
    assert read.status_code == 200
    assert read.json()["is_suspended"] is False


def test_report_deadline_purges_evidence_and_records_one_expiry(
    client, db, make_user, make_org, make_event, token_for
):
    reporter = make_user()
    owner = make_user()
    event = make_event(org=make_org(owner=owner))
    receipt = submit_report(client, event, reporter, token_for).json()
    report = db.get(EventReport, receipt["id"])
    deadline = report.deadline

    first_sweep = service.sweep_expired_reports(
        db, org_id=event.org_id, event_id=event.id, at=deadline
    )
    retry_sweep = service.sweep_expired_reports(
        db, org_id=event.org_id, event_id=event.id, at=deadline
    )
    db.refresh(report)
    expiry = db.scalar(
        select(SafetyAudit).where(
            SafetyAudit.report_id == report.id, SafetyAudit.action == "expire"
        )
    )

    assert first_sweep == 1
    assert retry_sweep == 0
    assert report.status == "expired" and report.version == 2
    assert report.evidence is None
    assert expiry.created_at == deadline


def test_history_dto_does_not_expose_idempotency_or_snapshot_payloads(
    client, make_user, make_org, make_event, token_for
):
    owner = make_user()
    event = make_event(org=make_org(owner=owner))
    changed = client.post(
        f"/api/v1/events/{event.id}/safety",
        json={"action": "hide", "version": 0, "client_key": str(uuid4())},
        headers=auth(owner, token_for),
    )
    history = client.get(
        f"/api/v1/organizations/{event.org_id}/safety-history",
        headers=auth(owner, token_for),
    )

    assert changed.status_code == 200
    assert history.status_code == 200
    assert history.json()
    assert set(history.json()[0]) == {
        "id", "org_id", "event_id", "report_id", "actor_id", "scope", "action",
        "version", "created_at",
    }
    assert not {"client_key", "payload_hash", "previous", "result"} & set(
        history.json()[0]
    )


def test_concurrent_exact_report_retries_create_one_report_and_audit(
    client, db, make_user, make_org, make_event, token_for
):
    reporter = make_user()
    event = make_event(org=make_org())
    request_key = uuid4()

    def send():
        return submit_report(
            client, event, reporter, token_for, key=request_key
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _index: send(), range(2)))

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    assert db.scalar(select(func.count(EventReport.id))) == 1
    assert db.scalar(
        select(func.count(SafetyAudit.id)).where(SafetyAudit.action == "report")
    ) == 1

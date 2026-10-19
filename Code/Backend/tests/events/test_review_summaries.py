from datetime import timedelta

from app.db.models import now
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration


def test_staff_summary_is_org_scoped_published_only_and_has_no_attendee_identity(
    client, db, make_user, make_org, make_event, token_for,
):
    org = make_org()
    moderator = make_user()
    member = make_user()
    event = make_event(org=org, registration_mode="approval", review_window_minutes=30, capacity=8)
    make_event(org=org, status="draft", published_at=None, title="Private draft")
    make_event(title="Different organization")
    db.add(OrgMembership(org_id=org.id, user_id=moderator.id, role="moderator", active=True))
    db.add(OrgMembership(org_id=org.id, user_id=member.id, role="member", active=True))
    deadline = now() + timedelta(minutes=25)
    for order, status in enumerate(["pending", "confirmed", "reconfirmation_required"], 1):
        user = make_user()
        db.add(Registration(user_id=user.id, event_id=event.id, status=status,
                            admission_order=order, review_deadline=deadline if status == "pending" else None))
    db.commit()
    path = f"/api/v1/organizations/{org.id}/review-events"
    response = client.get(path, headers={"Authorization": f"Bearer {token_for(moderator)}"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    summary = response.json()[0]
    assert summary["id"] == event.id
    assert summary["pending_registration_count"] == 1
    assert summary["confirmed_count"] == 1 and summary["reserved_count"] == 2
    assert summary["remaining_spots"] == 5
    assert summary["next_review_deadline"] is not None
    assert {"user_id", "email", "registrations", "draft_version", "created_by"}.isdisjoint(summary)
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": f"Bearer {token_for(member)}"}).status_code == 403
    assert client.get(path, headers={"Authorization": f"Bearer {token_for(make_user())}"}).status_code == 403


def test_review_summary_does_not_apply_discovery_end_boundary(
    client, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, starts_at=now() - timedelta(days=2), ends_at=now() - timedelta(days=1))
    result = client.get(f"/api/v1/organizations/{org.id}/review-events",
                        headers={"Authorization": f"Bearer {token_for(owner)}"})
    assert result.status_code == 200 and result.json()[0]["id"] == event.id
    assert result.json()[0]["pending_registration_count"] == 0
    assert result.json()[0]["next_review_deadline"] is None
    assert client.get("/api/v1/events").json() == []


def test_unapproved_or_ineligible_staff_cannot_read_review_summary(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner, accreditation_status="pending")
    make_event(org=org, status="draft", published_at=None)
    path = f"/api/v1/organizations/{org.id}/review-events"
    headers = {"Authorization": f"Bearer {token_for(owner)}"}
    assert client.get(path, headers=headers).status_code == 403
    org.accreditation_status = "approved"
    owner.email_verified = False
    db.commit()
    assert client.get(path, headers=headers).status_code == 403

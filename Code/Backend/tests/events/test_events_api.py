from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier, Event as ThreadEvent, Lock
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now, uid
from app.db.session import engine
from app.domains.events import routes as event_routes
from app.domains.events.models import Event
from app.domains.events.routes import create_organization_event, patch_event_draft
from app.domains.events.schemas import EventDraftInput
from app.domains.organizations.models import OrgMembership, Organization
from app.domains.organizations.service import decide_accreditation
from app.domains.registrations import service as registration_service


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def draft_body(**overrides):
    return {
        "title": "Fictional courtyard gathering",
        "summary": "",
        "description": "A fictional local event.",
        "starts_at": (now() + timedelta(days=2)).isoformat(),
        "ends_at": (now() + timedelta(days=2, hours=2)).isoformat(),
        "venue_name": "PLM courtyard",
        "venue_address": "Intramuros, Manila",
        "capacity": 8,
        "banner_key": "heritage",
        "cost_label": "Free",
        **overrides,
    }


def test_owner_can_save_incomplete_pending_draft_but_cannot_publish(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    pending_org = make_org(owner=owner, accreditation_status="pending")
    headers = auth(token_for(owner))

    created = client.post(f"/api/v1/organizations/{pending_org.id}/events", json={}, headers=headers)
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "draft"
    assert draft["title"] is None
    assert draft["starts_at"] is None
    assert draft["ends_at"] is None
    assert draft["summary"] == ""
    assert draft["created_by"] == owner.id
    assert draft["created_at"]
    preview = client.get(f"/api/v1/events/{draft['id']}/draft", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["title"] is None
    listed = client.get(f"/api/v1/organizations/{pending_org.id}/events", headers=headers)
    assert listed.status_code == 200
    assert [event["id"] for event in listed.json()] == [draft["id"]]
    stored = db.get(Event, draft["id"])
    assert stored.registration_mode == "instant"
    assert stored.review_window_minutes is None
    assert stored.material_revision == 0
    assert stored.event_type == "scheduled"
    assert stored.capacity is None

    patched = client.patch(
        f"/api/v1/events/{draft['id']}/draft",
        json={"title": "Pending organizations may continue drafting"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Pending organizations may continue drafting"

    denied = client.post(f"/api/v1/events/{draft['id']}/publish", headers=headers)
    assert denied.status_code == 403
    assert "Fictional" not in denied.text
    assert client.get(f"/api/v1/events/{draft['id']}/draft", headers=headers).json()["status"] == "draft"


def test_rejected_organization_can_read_private_drafts_but_not_mutate_them(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="rejected")
    draft = make_event(org=organization, status="draft", published_at=None)
    headers = auth(token_for(owner))

    listed = client.get(f"/api/v1/organizations/{organization.id}/events", headers=headers)
    assert listed.status_code == 200
    assert [event["id"] for event in listed.json()] == [draft.id]
    private_read = client.get(f"/api/v1/events/{draft.id}/draft", headers=headers)
    assert private_read.status_code == 200
    assert private_read.json()["id"] == draft.id
    event_count = db.scalar(select(func.count(Event.id)).where(Event.org_id == organization.id))

    create = client.post(
        f"/api/v1/organizations/{organization.id}/events", json={}, headers=headers
    )
    assert create.status_code == 409
    assert create.json()["error"]["code"] == "organization_rejected_read_only"
    assert db.scalar(select(func.count(Event.id)).where(Event.org_id == organization.id)) == event_count

    patch = client.patch(
        f"/api/v1/events/{draft.id}/draft",
        json={"title": "Must remain unchanged"},
        headers=headers,
    )
    assert patch.status_code == 409
    assert patch.json()["error"]["code"] == "organization_rejected_read_only"
    unchanged = client.get(f"/api/v1/events/{draft.id}/draft", headers=headers)
    assert unchanged.status_code == 200
    assert unchanged.json()["title"] == draft.title
    assert db.scalar(select(Event.title).where(Event.id == draft.id)) == draft.title

    publish = client.post(f"/api/v1/events/{draft.id}/publish", headers=headers)
    assert publish.status_code == 403


def test_only_active_owner_or_admin_can_create_and_edit_drafts(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    admin = make_user()
    member = make_user()
    moderator = make_user()
    inactive_admin = make_user()
    organization = make_org(owner=owner, accreditation_status="pending")
    foreign_owner = make_user()
    make_org(owner=foreign_owner)
    db.add_all(
        [
            OrgMembership(id=uid(), org_id=organization.id, user_id=admin.id, role="admin", active=True),
            OrgMembership(id=uid(), org_id=organization.id, user_id=member.id, role="member", active=True),
            OrgMembership(id=uid(), org_id=organization.id, user_id=moderator.id, role="moderator", active=True),
            OrgMembership(id=uid(), org_id=organization.id, user_id=inactive_admin.id, role="admin", active=False),
        ]
    )
    db.commit()
    draft = make_event(org=organization, status="draft", published_at=None)
    event_count = db.scalar(select(func.count(Event.id)).where(Event.org_id == organization.id))

    for actor in (member, moderator, inactive_admin, foreign_owner):
        headers = auth(token_for(actor))
        assert client.get(f"/api/v1/organizations/{organization.id}/events", headers=headers).status_code == 403
        assert client.get(f"/api/v1/events/{draft.id}/draft", headers=headers).status_code == 403
        assert client.post(f"/api/v1/organizations/{organization.id}/events", json={}, headers=headers).status_code == 403
        assert client.patch(
            f"/api/v1/events/{draft.id}/draft", json={"title": "Must not be saved"}, headers=headers
        ).status_code == 403
        assert client.post(f"/api/v1/events/{draft.id}/publish", headers=headers).status_code == 403

    assert client.get(f"/api/v1/organizations/{organization.id}/events").status_code == 401
    assert client.get(f"/api/v1/events/{draft.id}/draft").status_code == 401
    assert client.post(f"/api/v1/organizations/{organization.id}/events", json={}).status_code == 401
    assert client.patch(f"/api/v1/events/{draft.id}/draft", json={"title": "Guest"}).status_code == 401
    assert client.post(f"/api/v1/events/{draft.id}/publish").status_code == 401
    assert db.scalar(select(Event.title).where(Event.id == draft.id)) == draft.title
    assert db.scalar(select(func.count(Event.id)).where(Event.org_id == organization.id)) == event_count

    allowed = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={},
        headers=auth(token_for(admin)),
    )
    assert allowed.status_code == 201
    edited = client.patch(
        f"/api/v1/events/{allowed.json()['id']}/draft",
        json={"title": "Admin-owned draft"},
        headers=auth(token_for(admin)),
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Admin-owned draft"


def test_draft_writes_refresh_stale_organization_after_rejection(
    db, make_user, make_org, make_event
):
    owner = make_user()
    admin = make_user(platform_admin=True)
    organization = make_org(owner=owner, accreditation_status="pending")
    draft = make_event(org=organization, status="draft", title="Original draft", published_at=None)
    stale_organization = db.get(Organization, organization.id)
    assert stale_organization.accreditation_status == "pending"
    patch_db = Session(engine(), expire_on_commit=False)
    stale_patch_organization = patch_db.get(Organization, organization.id)
    assert stale_patch_organization.accreditation_status == "pending"
    patch_db.get(Event, draft.id)

    admin_actor = Actor(
        user_id=admin.id,
        nickname=admin.nickname,
        eligible=True,
        profile_complete=True,
        platform_admin=True,
    )
    try:
        with Session(engine(), expire_on_commit=False) as decision_db:
            decide_accreditation(decision_db, admin_actor, organization.id, "rejected")
            decision_db.commit()

        owner_actor = Actor(
            user_id=owner.id,
            nickname=owner.nickname,
            eligible=True,
            profile_complete=True,
            platform_admin=False,
        )
        with pytest.raises(DomainError) as denied_create:
            create_organization_event(UUID(organization.id), EventDraftInput(), db, owner_actor)
        assert denied_create.value.code == "organization_rejected_read_only"
        # Direct route calls do not run get_db's dependency cleanup. Check that
        # the locked read refreshed this object, then release its row lock before
        # asking the independent patch session to acquire the same lock.
        assert stale_organization.accreditation_status == "rejected"
        db.rollback()

        with pytest.raises(DomainError) as denied_patch:
            patch_event_draft(
                UUID(draft.id), EventDraftInput(title="Must stay unchanged"), patch_db, owner_actor
            )

        assert denied_patch.value.code == "organization_rejected_read_only"
        assert stale_patch_organization.accreditation_status == "rejected"
        patch_db.rollback()
        assert db.scalar(select(func.count(Event.id)).where(Event.org_id == organization.id)) == 1
        assert db.scalar(select(Event.title).where(Event.id == draft.id)) == "Original draft"
    finally:
        patch_db.close()


def test_concurrent_publish_uses_event_state_after_organization_lock(
    make_user, make_org, make_event, token_for, monkeypatch,
):
    from fastapi.testclient import TestClient

    from app.main import create_app

    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="approved")
    event = make_event(org=organization, status="draft", published_at=None)
    headers = auth(token_for(owner))
    both_loaded = Barrier(2)
    original_event_lookup = event_routes._event_or_404

    def lookup_then_wait(session, event_id):
        loaded = original_event_lookup(session, event_id)
        if loaded.id == event.id:
            both_loaded.wait(timeout=10)
        return loaded

    monkeypatch.setattr(event_routes, "_event_or_404", lookup_then_wait)

    def publish_once():
        with TestClient(create_app()) as request_client:
            return request_client.post(f"/api/v1/events/{event.id}/publish", headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _index: publish_once(), range(2)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "published_event_immutable"


def test_draft_patch_refreshes_event_after_waiting_for_organization_lock(
    client, make_user, make_org, make_event, token_for, monkeypatch,
):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from app.main import create_app

    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="approved")
    event = make_event(org=organization, status="draft", published_at=None)
    headers = auth(token_for(owner))
    patch_loaded = ThreadEvent()
    allow_patch = ThreadEvent()
    lookup_lock = Lock()
    lookup_count = 0
    original_event_lookup = event_routes._event_or_404

    def lookup_then_pause_first_request(session, event_id):
        nonlocal lookup_count
        loaded = original_event_lookup(session, event_id)
        with lookup_lock:
            lookup_count += 1
            pause = lookup_count == 1
        if pause:
            patch_loaded.set()
            if not allow_patch.wait(timeout=10):
                raise RuntimeError("patch test synchronization timed out")
        return loaded

    monkeypatch.setattr(event_routes, "_event_or_404", lookup_then_pause_first_request)

    def patch_once():
        with TestClient(create_app()) as request_client:
            return request_client.patch(
                f"/api/v1/events/{event.id}/draft",
                json={"title": "Must not overwrite a published event"},
                headers=headers,
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        patch_future = pool.submit(patch_once)
        try:
            assert patch_loaded.wait(timeout=10)
            published = client.post(f"/api/v1/events/{event.id}/publish", headers=headers)
            assert published.status_code == 200
        finally:
            allow_patch.set()
        patched = patch_future.result(timeout=10)

    assert patched.status_code == 409
    assert patched.json()["error"]["code"] == "published_event_immutable"
    # Read the committed row through a new request-backed Session after the race.
    from app.db.session import session_factory

    with session_factory()() as verification_db:
        stored_event = verification_db.get(Event, event.id)
    assert stored_event.status == "published"
    assert stored_event.title == "Fictional campus gathering"


@pytest.mark.parametrize("banner", ["heritage", "design", "garden", "music"])
def test_fixture_banner_allowlist_accepts_all_supported_keys(
    client, make_user, make_org, token_for, banner
):
    owner = make_user()
    organization = make_org(owner=owner)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={"banner_key": banner},
        headers=auth(token_for(owner)),
    )
    assert response.status_code == 201
    assert response.json()["banner_key"] == banner


def test_draft_input_boundaries_are_rejected_without_echoing_values(client, make_user, make_org, token_for):
    owner = make_user()
    organization = make_org(owner=owner)
    headers = auth(token_for(owner))
    bad_bodies = [
        {"title": "x" * 201},
        {"venue_name": "x" * 201},
        {"venue_address": "x" * 501},
        {"cost_label": "x" * 101},
        {"capacity": 0},
        {"capacity": True},
        {"review_window_minutes": 14},
        {"review_window_minutes": 2881},
        {"banner_key": "private-upload"},
        {"starts_at": "2030-01-01T10:00:00"},
        {"summary": None},
        {"status": "published"},
        {"unexpected": "do-not-echo-this-value"},
    ]

    for body in bad_bodies:
        response = client.post(
            f"/api/v1/organizations/{organization.id}/events", json=body, headers=headers
        )
        assert response.status_code == 422
        assert "do-not-echo-this-value" not in response.text

    at_limit = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={
            "title": "x" * 200,
            "venue_name": "v" * 200,
            "venue_address": "a" * 500,
            "cost_label": "c" * 100,
            "capacity": 1,
            "banner_key": "music",
        },
        headers=headers,
    )
    assert at_limit.status_code == 201


def test_publish_requires_complete_future_event_and_rejects_invalid_lifecycle(client, db, make_user, make_org, make_event, token_for):
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="approved")
    private_title = "PRIVATE_DRAFT_VALUE_MUST_NOT_LEAK_73f0"
    event = make_event(
        org=organization,
        status="draft",
        title=private_title,
        description=None,
        starts_at=None,
        ends_at=None,
        venue_name=None,
        venue_address=None,
        capacity=None,
        banner_key=None,
        published_at=None,
    )
    headers = auth(token_for(owner))
    path = f"/api/v1/events/{event.id}/publish"

    private_draft = client.get(f"/api/v1/events/{event.id}/draft", headers=headers)
    assert private_draft.status_code == 200
    assert private_draft.json()["title"] == private_title

    incomplete = client.post(path, headers=headers)
    assert incomplete.status_code == 422
    assert incomplete.json()["error"]["code"] == "event_fields_required"
    assert private_title not in incomplete.text

    past_start = (now() - timedelta(minutes=1)).isoformat()
    bad_date = client.patch(
        f"/api/v1/events/{event.id}/draft",
        json=draft_body(starts_at=past_start),
        headers=headers,
    )
    assert bad_date.status_code == 200
    rejected = client.post(path, headers=headers)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "event_start_must_be_future"

    reversed_times = client.patch(
        f"/api/v1/events/{event.id}/draft",
        json=draft_body(
            starts_at=(now() + timedelta(days=2)).isoformat(),
            ends_at=(now() + timedelta(days=1)).isoformat(),
        ),
        headers=headers,
    )
    assert reversed_times.status_code == 200
    end_before_start = client.post(path, headers=headers)
    assert end_before_start.status_code == 422
    assert end_before_start.json()["error"]["code"] == "event_end_must_follow_start"

    valid = client.patch(
        f"/api/v1/events/{event.id}/draft", json=draft_body(), headers=headers
    )
    assert valid.status_code == 200
    published = client.post(path, headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published_at"]

    edit = client.patch(
        f"/api/v1/events/{event.id}/draft", json={"title": "Changed"}, headers=headers
    )
    assert edit.status_code == 409
    assert client.post(f"/api/v1/events/{event.id}/cancel", headers=headers).status_code == 404


def test_approval_draft_needs_a_review_window_before_publication(client, make_user, make_org, token_for):
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="approved")
    headers = auth(token_for(owner))
    created = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json=draft_body(registration_mode="approval"),
        headers=headers,
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["registration_mode"] == "approval"
    assert draft["review_window_minutes"] is None
    assert draft["material_revision"] == 0

    missing_window = client.post(f"/api/v1/events/{draft['id']}/publish", headers=headers)
    assert missing_window.status_code == 422
    assert missing_window.json()["error"]["code"] == "event_review_window_invalid"

    completed = client.patch(
        f"/api/v1/events/{draft['id']}/draft",
        json={"review_window_minutes": 15},
        headers=headers,
    )
    assert completed.status_code == 200
    published = client.post(f"/api/v1/events/{draft['id']}/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["registration_mode"] == "approval"
    assert published.json()["review_window_minutes"] == 15
    assert published.json()["material_revision"] == 0


def test_material_change_reconciles_before_applying_full_merged_fields(
    client, db, make_user, make_org, make_event, token_for, monkeypatch
):
    owner = make_user()
    admin = make_user()
    organization = make_org(owner=owner)
    db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=admin.id, role="admin", active=True))
    db.commit()
    event = make_event(org=organization, capacity=5)
    calls = []

    def reconcile(db_arg, event_arg, fields, deadline, selection_mode, selected_registration_ids):
        calls.append(
            {
                "revision": event_arg.material_revision,
                "fields": fields.copy(),
                "deadline": deadline,
                "selection_mode": selection_mode,
                "selected_registration_ids": list(selected_registration_ids),
            }
        )

    monkeypatch.setattr(
        registration_service, "reconcile_material_change", reconcile, raising=False
    )
    starts_at = now() + timedelta(days=3)
    ends_at = starts_at + timedelta(hours=3)
    first = client.post(
        f"/api/v1/events/{event.id}/changes",
        json={
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "reconfirm_deadline": (now() + timedelta(days=1)).isoformat(),
        },
        headers=auth(token_for(owner)),
    )

    assert first.status_code == 200
    response_start = datetime.fromisoformat(first.json()["starts_at"].replace("Z", "+00:00"))
    assert response_start == starts_at
    assert first.json()["material_revision"] == 1
    assert calls[0]["revision"] == 0
    assert calls[0]["selection_mode"] == "exact"
    assert calls[0]["selected_registration_ids"] == []
    assert calls[0]["fields"] == {
        "starts_at": starts_at,
        "ends_at": ends_at,
        "venue_name": event.venue_name,
        "venue_address": event.venue_address,
        "capacity": 5,
        "cost_label": event.cost_label,
    }

    second = client.post(
        f"/api/v1/events/{event.id}/changes",
        json={
            "cost_label": "PHP 100",
            "reconfirm_deadline": (now() + timedelta(days=1)).isoformat(),
            "selection_mode": "newest_in_pool",
            "selected_registration_ids": [str(UUID(int=1))],
        },
        headers=auth(token_for(admin)),
    )

    assert second.status_code == 200
    assert second.json()["material_revision"] == 2
    assert calls[1]["revision"] == 1
    assert calls[1]["selection_mode"] == "newest_in_pool"
    assert calls[1]["selected_registration_ids"] == [str(UUID(int=1))]
    assert calls[1]["fields"]["cost_label"] == "PHP 100"


def test_material_change_requires_a_manager_and_a_published_event(
    client, db, make_user, make_org, make_event, token_for, monkeypatch
):
    owner = make_user()
    moderator = make_user()
    organization = make_org(owner=owner)
    db.add(
        OrgMembership(
            id=uid(), org_id=organization.id, user_id=moderator.id, role="moderator", active=True
        )
    )
    db.commit()
    event = make_event(org=organization)
    draft = make_event(org=organization, status="draft", published_at=None)
    calls = []
    monkeypatch.setattr(
        registration_service,
        "reconcile_material_change",
        lambda *args: calls.append(args),
        raising=False,
    )
    payload = {
        "starts_at": (now() + timedelta(days=3)).isoformat(),
        "reconfirm_deadline": (now() + timedelta(days=1)).isoformat(),
    }

    forbidden = client.post(
        f"/api/v1/events/{event.id}/changes",
        json=payload,
        headers=auth(token_for(moderator)),
    )
    draft_response = client.post(
        f"/api/v1/events/{draft.id}/changes",
        json=payload,
        headers=auth(token_for(owner)),
    )

    assert forbidden.status_code == 403
    assert draft_response.status_code == 409
    assert draft_response.json()["error"]["code"] == "event_change_requires_published"
    assert calls == []


def test_material_change_rejects_noop_and_invalid_deadline_before_reconciliation(
    client, make_user, make_org, make_event, token_for, monkeypatch
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization)
    calls = []
    monkeypatch.setattr(
        registration_service,
        "reconcile_material_change",
        lambda *args: calls.append(args),
        raising=False,
    )

    no_change = client.post(
        f"/api/v1/events/{event.id}/changes",
        json={"reconfirm_deadline": (now() + timedelta(days=1)).isoformat()},
        headers=auth(token_for(owner)),
    )
    new_start = now() + timedelta(days=3)
    bad_deadline = client.post(
        f"/api/v1/events/{event.id}/changes",
        json={
            "starts_at": new_start.isoformat(),
            "ends_at": (new_start + timedelta(hours=2)).isoformat(),
            "reconfirm_deadline": new_start.isoformat(),
        },
        headers=auth(token_for(owner)),
    )

    assert no_change.status_code == 422
    assert no_change.json()["error"]["code"] == "event_material_change_required"
    assert bad_deadline.status_code == 422
    assert bad_deadline.json()["error"]["code"] == "event_reconfirmation_deadline_invalid"
    assert calls == []


def test_public_search_sort_and_projection_hide_private_fields(client, db, make_user, make_org, make_event):
    owner = make_user()
    org = make_org(owner=owner, name="Campus Arts Society")
    later = make_event(
        org=org,
        title="100% Real Workshop",
        starts_at=now() + timedelta(days=4),
        ends_at=now() + timedelta(days=4, hours=2),
        capacity=5,
        interest_count=7,
    )
    earlier = make_event(
        org=org,
        title="Earlier Design Session",
        starts_at=now() + timedelta(days=1),
        ends_at=now() + timedelta(days=1, hours=2),
        capacity=4,
        published_at=now() - timedelta(days=1),
    )
    ended = make_event(
        org=org,
        title="Past workshop",
        starts_at=now() - timedelta(days=2),
        ends_at=now() - timedelta(days=1),
    )
    from app.domains.registrations.models import Registration, RegistrationReceipt

    confirmed_user = make_user()
    waitlisted_user = make_user()
    cancelled_user = make_user()
    pending_receipt_user = make_user()
    pending_user = make_user()
    reconfirmation_user = make_user()
    db.add_all(
        [
            Registration(
                id=uid(), user_id=confirmed_user.id, event_id=later.id, status="confirmed", admission_order=1
            ),
            Registration(
                id=uid(), user_id=waitlisted_user.id, event_id=later.id, status="waitlisted", admission_order=2
            ),
            Registration(
                id=uid(), user_id=cancelled_user.id, event_id=later.id, status="cancelled", admission_order=3
            ),
            Registration(
                id=uid(), user_id=pending_user.id, event_id=later.id, status="pending", admission_order=4
            ),
            Registration(
                id=uid(), user_id=reconfirmation_user.id, event_id=later.id,
                status="reconfirmation_required", admission_order=5,
            ),
            RegistrationReceipt(
                id=uid(),
                user_id=pending_receipt_user.id,
                event_id=later.id,
                idempotency_key="search-catchup-key",
                event_order=6,
            ),
        ]
    )
    db.commit()

    upcoming = client.get("/api/v1/events")
    assert upcoming.status_code == 200
    upcoming_events = upcoming.json()
    assert [item["id"] for item in upcoming_events] == [earlier.id, later.id]
    assert ended.id not in {item["id"] for item in upcoming_events}
    card = next(item for item in upcoming_events if item["id"] == later.id)
    assert card["organization_name"] == "Campus Arts Society"
    # Public reads expose committed registrations without draining receipts.
    assert card["confirmed_count"] == 1
    assert card["reserved_count"] == 2
    assert card["remaining_spots"] == 2
    assert db.scalar(
        select(RegistrationReceipt.processed_at).where(
            RegistrationReceipt.idempotency_key == "search-catchup-key"
        )
    ) is None
    assert card["interest_count"] == 7
    assert card["registration_mode"] == "instant"
    assert card["review_window_minutes"] is None
    assert card["material_revision"] == 0
    assert "created_by" not in card and "created_at" not in card
    assert "email" not in card and "attendees" not in card
    assert set(card) == {
        "id", "org_id", "organization_name", "title", "summary", "description",
        "starts_at", "ends_at", "venue_name", "venue_address", "capacity",
        "confirmed_count", "reserved_count", "remaining_spots", "interest_count", "banner_key", "banner_url",
        "cost_label", "registration_mode", "review_window_minutes", "material_revision",
        "status", "published_at", "event_type", "tags", "coarse_area", "recommendation_reasons", "is_featured", "registration_available",
    }

    newest = client.get("/api/v1/events", params={"sort": "newest"})
    assert [item["id"] for item in newest.json()] == [later.id, earlier.id]

    literal_percent = client.get("/api/v1/events", params={"q": "%"})
    assert [item["id"] for item in literal_percent.json()] == [later.id]
    literal_underscore = client.get("/api/v1/events", params={"q": "_"})
    assert literal_underscore.json() == []
    org_search = client.get("/api/v1/events", params={"q": "cAmPuS aRtS"})
    assert {item["id"] for item in org_search.json()} == {earlier.id, later.id}
    private_field_search = client.get("/api/v1/events", params={"q": "Intramuros"})
    assert private_field_search.json() == []

    historical = client.get(f"/api/v1/events/{ended.id}")
    assert historical.status_code == 200
    assert historical.json()["id"] == ended.id


def test_my_clubs_requires_eligible_actor_and_composes_with_search(client, db, make_user, make_org, make_event, token_for):
    owner = make_user()
    member = make_user()
    other_owner = make_user()
    inactive_member_owner = make_user()
    member_org = make_org(owner=owner, name="Arts Collective")
    other_org = make_org(owner=other_owner, name="Garden Society")
    inactive_member_org = make_org(owner=inactive_member_owner, name="Arts Alumni")
    db.add_all(
        [
            OrgMembership(id=uid(), org_id=member_org.id, user_id=member.id, role="member", active=True),
            OrgMembership(id=uid(), org_id=inactive_member_org.id, user_id=member.id, role="member", active=False),
        ]
    )
    db.commit()
    in_club = make_event(org=member_org, title="Arts studio night")
    make_event(org=other_org, title="Arts garden night")
    make_event(org=inactive_member_org, title="Arts alumni night")

    guest = client.get("/api/v1/events", params={"my_clubs": "true"})
    assert guest.status_code == 401
    ineligible = make_user(email="fictional-ineligible@example.com")
    denied = client.get(
        "/api/v1/events",
        params={"my_clubs": "true"},
        headers=auth(token_for(ineligible)),
    )
    assert denied.status_code == 403

    result = client.get(
        "/api/v1/events",
        params={"my_clubs": "true", "q": "Arts"},
        headers=auth(token_for(member)),
    )
    assert result.status_code == 200
    assert [item["id"] for item in result.json()] == [in_club.id]


def test_private_draft_routes_require_manager_and_public_routes_hide_drafts(client, make_user, make_org, make_event, token_for):
    owner = make_user()
    visitor = make_user()
    organization = make_org(owner=owner)
    draft = make_event(org=organization, status="draft", published_at=None)

    denied = client.get(f"/api/v1/events/{draft.id}/draft", headers=auth(token_for(visitor)))
    assert denied.status_code == 403
    public_detail = client.get(f"/api/v1/events/{draft.id}")
    assert public_detail.status_code == 404
    assert client.get("/api/v1/events").json() == []

    private = client.get(f"/api/v1/events/{draft.id}/draft", headers=auth(token_for(owner)))
    assert private.status_code == 200
    assert private.json()["created_by"] == owner.id

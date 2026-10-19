from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.events.recommendations import matched_reason_codes
from app.domains.events.schemas import EventDraftInput
from app.domains.events.service import validate_material_change, validate_publishable
from app.domains.identity.discovery_models import UserDiscoveryPreferences
from app.domains.organizations.models import OrgMembership


EVENTS_URL = "/api/v1/events"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _flash_draft(starts_at, *, published_at=None, **overrides):
    fields = {
        "id": "flash-event",
        "org_id": "organization-id",
        "created_by": "user-id",
        "title": "Fictional flash event",
        "summary": "",
        "description": "A fictional local gathering.",
        "starts_at": starts_at,
        "ends_at": starts_at + timedelta(hours=1),
        "venue_name": "PLM courtyard",
        "venue_address": "Intramuros, Manila",
        "capacity": 8,
        "banner_key": "heritage",
        "cost_label": "Free",
        "status": "draft",
        "registration_mode": "instant",
        "review_window_minutes": None,
        "event_type": "flash",
        "published_at": published_at,
        "material_revision": 0,
        "next_admission": 0,
        "interest_count": 0,
    }
    fields.update(overrides)
    return Event(**fields)


def _event_record(
    organization,
    *,
    title,
    starts_at,
    ends_at,
    published_at,
    event_type="scheduled",
    coarse_area=None,
    tags=(),
    event_id=None,
):
    return Event(
        id=event_id or uid(),
        org_id=organization.id,
        created_by=organization.created_by,
        title=title,
        summary="",
        description="A fictional local gathering.",
        starts_at=starts_at,
        ends_at=ends_at,
        venue_name="PLM courtyard",
        venue_address="Intramuros, Manila",
        capacity=8,
        banner_key="heritage",
        cost_label="Free",
        status="published",
        registration_mode="instant",
        review_window_minutes=None,
        event_type=event_type,
        tags=list(tags),
        coarse_area=coarse_area,
        published_at=published_at,
        material_revision=0,
        next_admission=0,
        interest_count=0,
    )


@pytest.mark.parametrize(
    ("start_offset", "error_code"),
    [
        (timedelta(0), "event_start_must_be_future"),
        (timedelta(microseconds=1), None),
        (timedelta(hours=24), None),
        (timedelta(hours=24, microseconds=1), "event_flash_start_window_invalid"),
    ],
)
def test_flash_publish_window_has_strict_lower_and_inclusive_24_hour_upper_bound(
    start_offset, error_code
):
    published_at = datetime(2032, 1, 1, tzinfo=timezone.utc)
    event = _flash_draft(published_at + start_offset)

    if error_code:
        with pytest.raises(DomainError) as error:
            validate_publishable(event, at=published_at)
        assert error.value.code == error_code
    else:
        validate_publishable(event, at=published_at)


def test_flash_material_reschedule_stays_in_the_original_publication_window():
    published_at = datetime(2032, 1, 1, tzinfo=timezone.utc)
    validation_time = published_at + timedelta(hours=1)
    event = _flash_draft(
        published_at + timedelta(hours=12),
        published_at=published_at,
        status="published",
    )
    new_start = published_at + timedelta(hours=24)
    deadline = published_at + timedelta(hours=12)

    proposed = validate_material_change(
        event,
        {"starts_at": new_start, "ends_at": new_start + timedelta(hours=1)},
        deadline,
        at=validation_time,
    )
    assert proposed["starts_at"] == new_start

    with pytest.raises(DomainError) as outside_original_window:
        validate_material_change(
            event,
            {
                "starts_at": new_start + timedelta(microseconds=1),
                "ends_at": new_start + timedelta(hours=1, microseconds=1),
            },
            deadline,
            at=validation_time,
        )
    assert outside_original_window.value.code == "event_flash_start_window_invalid"


def test_flash_draft_partial_updates_validate_effective_mode_and_keep_draft_private(
    client, make_user, make_org, token_for
):
    assert EventDraftInput().event_type == "scheduled"

    owner = make_user()
    organization = make_org(owner=owner)
    headers = auth(token_for(owner))

    created = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={"title": "PRIVATE_FLASH_DRAFT", "event_type": "flash"},
        headers=headers,
    )
    assert created.status_code == 201
    flash_draft = created.json()
    assert flash_draft["event_type"] == "flash"
    assert flash_draft["registration_mode"] == "instant"
    assert flash_draft["review_window_minutes"] is None
    assert client.get(f"{EVENTS_URL}/{flash_draft['id']}").status_code == 404
    assert "PRIVATE_FLASH_DRAFT" not in client.get(EVENTS_URL).text

    rejected_partial_mode = client.patch(
        f"{EVENTS_URL}/{flash_draft['id']}/draft",
        json={"registration_mode": "approval"},
        headers=headers,
    )
    assert rejected_partial_mode.status_code == 422
    current = client.get(f"{EVENTS_URL}/{flash_draft['id']}/draft", headers=headers).json()
    assert current["event_type"] == "flash"
    assert current["registration_mode"] == "instant"

    approval_draft = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={"registration_mode": "approval", "review_window_minutes": 30},
        headers=headers,
    ).json()
    rejected_type_only = client.patch(
        f"{EVENTS_URL}/{approval_draft['id']}/draft",
        json={"event_type": "flash"},
        headers=headers,
    )
    assert rejected_type_only.status_code == 422

    changed = client.patch(
        f"{EVENTS_URL}/{approval_draft['id']}/draft",
        json={
            "event_type": "flash",
            "registration_mode": "instant",
            "review_window_minutes": None,
        },
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["event_type"] == "flash"
    assert changed.json()["draft_version"] != approval_draft["draft_version"]
    stale_edit = client.patch(
        f"{EVENTS_URL}/{approval_draft['id']}/draft",
        json={"title": "Stale write must not apply"},
        headers={**headers, "If-Match": f'"{approval_draft["draft_version"]}"'},
    )
    assert stale_edit.status_code == 409
    assert stale_edit.json()["error"]["code"] == "draft_conflict"

    invalid_create = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={
            "event_type": "flash",
            "registration_mode": "approval",
            "review_window_minutes": 30,
        },
        headers=headers,
    )
    assert invalid_create.status_code == 422
    invalid_review_window = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={
            "event_type": "flash",
            "registration_mode": "instant",
            "review_window_minutes": 15,
        },
        headers=headers,
    )
    assert invalid_review_window.status_code == 422


def test_pending_flash_publish_is_denied_and_approved_flash_uses_one_publication_time(
    client, make_user, make_org, token_for, monkeypatch
):
    from app.domains.events import routes as event_routes
    from app.domains.events import service as event_service

    owner = make_user()
    pending = make_org(owner=owner, accreditation_status="pending")
    approved = make_org(owner=owner, accreditation_status="approved")
    publication_time = datetime(2032, 2, 3, 4, 5, tzinfo=timezone.utc)
    starts_at = publication_time + timedelta(hours=24)
    headers = auth(token_for(owner))

    def create_flash(org):
        return client.post(
            f"/api/v1/organizations/{org.id}/events",
            json={
                "title": "Fictional Flash gathering",
                "description": "A fictional event description.",
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                "venue_name": "PLM courtyard",
                "venue_address": "Intramuros, Manila",
                "capacity": 8,
                "banner_key": "heritage",
                "event_type": "flash",
            },
            headers=headers,
        )

    pending_draft = create_flash(pending)
    assert pending_draft.status_code == 201
    denied = client.post(f"{EVENTS_URL}/{pending_draft.json()['id']}/publish", headers=headers)
    assert denied.status_code == 403

    approved_draft = create_flash(approved)
    assert approved_draft.status_code == 201
    monkeypatch.setattr(event_routes, "now", lambda: publication_time)
    monkeypatch.setattr(event_service, "now", lambda: publication_time + timedelta(seconds=1))
    published = client.post(
        f"{EVENTS_URL}/{approved_draft.json()['id']}/publish",
        headers={**headers, "If-Match": f'"{approved_draft.json()["draft_version"]}"'},
    )
    assert published.status_code == 200
    assert published.json()["event_type"] == "flash"
    assert datetime.fromisoformat(published.json()["published_at"].replace("Z", "+00:00")) == publication_time
    assert datetime.fromisoformat(published.json()["starts_at"].replace("Z", "+00:00")) == starts_at

    stale_publish = client.post(
        f"{EVENTS_URL}/{approved_draft.json()['id']}/publish",
        headers={**headers, "If-Match": f'"{approved_draft.json()["draft_version"]}"'},
    )
    assert stale_publish.status_code == 409
    immutable_type = client.patch(
        f"{EVENTS_URL}/{approved_draft.json()['id']}/draft",
        json={"event_type": "scheduled"},
        headers=headers,
    )
    assert immutable_type.status_code == 409


def test_for_you_flash_boost_boundaries_club_priority_and_private_reasons(
    client, db, make_user, make_org, token_for, monkeypatch
):
    from app.domains.events import routes as event_routes

    member = make_user(tags=["arts", "PRIVATE_PROFILE_TOPIC"])
    club = make_org()
    outside = make_org()
    request_now = now().replace(microsecond=0)
    full_week = [
        {"weekday": weekday, "start_minute": 0, "end_minute": 1440}
        for weekday in range(7)
    ]
    db.add_all(
        [
            OrgMembership(
                id=uid(), org_id=club.id, user_id=member.id, role="member", active=True
            ),
            UserDiscoveryPreferences(
                user_id=member.id,
                coarse_area="intramuros",
                availability=full_week,
            ),
        ]
    )
    events = [
        _event_record(
            club,
            title="Club active flash",
            starts_at=request_now + timedelta(hours=6),
            ends_at=request_now + timedelta(hours=7),
            published_at=request_now - timedelta(minutes=1),
            event_type="flash",
            coarse_area="intramuros",
            tags=["arts"],
        ),
        _event_record(
            club,
            title="Club scheduled event",
            starts_at=request_now + timedelta(hours=5),
            ends_at=request_now + timedelta(hours=6),
            published_at=request_now - timedelta(days=1),
        ),
        _event_record(
            outside,
            title="Outside active flash",
            starts_at=request_now + timedelta(hours=8),
            ends_at=request_now + timedelta(hours=9),
            published_at=request_now,
            event_type="flash",
            coarse_area="intramuros",
            tags=["arts"],
        ),
        _event_record(
            outside,
            title="Expired flash",
            starts_at=request_now + timedelta(minutes=30),
            ends_at=request_now + timedelta(hours=1, minutes=30),
            published_at=request_now - timedelta(hours=3),
            event_type="flash",
            coarse_area="intramuros",
            tags=["arts"],
        ),
        _event_record(
            outside,
            title="Flash at start boundary",
            starts_at=request_now,
            ends_at=request_now + timedelta(hours=1),
            published_at=request_now - timedelta(minutes=1),
            event_type="flash",
            coarse_area="intramuros",
            tags=["arts"],
        ),
        _event_record(
            outside,
            title="Flash without area",
            starts_at=request_now + timedelta(hours=2),
            ends_at=request_now + timedelta(hours=3),
            published_at=request_now - timedelta(minutes=1),
            event_type="flash",
            tags=["arts"],
        ),
        _event_record(
            outside,
            title="Flash with another area",
            starts_at=request_now + timedelta(hours=3),
            ends_at=request_now + timedelta(hours=4),
            published_at=request_now - timedelta(minutes=1),
            event_type="flash",
            coarse_area="quezon city",
            tags=["arts"],
        ),
    ]
    db.add_all(events)
    db.commit()
    monkeypatch.setattr(event_routes, "now", lambda: request_now)

    response = client.get(EVENTS_URL, params={"sort": "for_you"}, headers=auth(token_for(member)))
    assert response.status_code == 200
    cards = response.json()
    event_by_title = {card["title"]: card for card in cards}
    assert [card["title"] for card in cards].index("Club active flash") < [
        card["title"] for card in cards
    ].index("Outside active flash")
    assert [card["title"] for card in cards].index("Outside active flash") < [
        card["title"] for card in cards
    ].index("Expired flash")
    assert event_by_title["Club active flash"]["recommendation_reasons"] == [
        "club", "flash", "interests", "area", "availability"
    ]
    assert event_by_title["Outside active flash"]["recommendation_reasons"] == [
        "flash", "interests", "area", "availability"
    ]
    assert "flash" not in event_by_title["Expired flash"]["recommendation_reasons"]
    assert "flash" not in event_by_title["Flash at start boundary"]["recommendation_reasons"]
    assert event_by_title["Flash without area"]["recommendation_reasons"] == [
        "interests", "availability"
    ]
    assert event_by_title["Flash with another area"]["recommendation_reasons"] == [
        "interests", "availability"
    ]
    assert "PRIVATE_PROFILE_TOPIC" not in response.text
    assert matched_reason_codes(0, 1, 1, 1) == ["interests", "area", "availability"]
    assert matched_reason_codes(0, 1, 1, 1, 1) == [
        "flash", "interests", "area", "availability"
    ]

    guest_for_you = client.get(EVENTS_URL, params={"sort": "for_you"})
    assert guest_for_you.status_code == 200
    guest_cards = guest_for_you.json()
    assert datetime.fromisoformat(guest_cards[0]["starts_at"].replace("Z", "+00:00")) == request_now
    assert all(card["recommendation_reasons"] == [] for card in guest_cards)
    assert any(card["event_type"] == "flash" for card in guest_cards)


@pytest.mark.parametrize("sort", ["upcoming", "newest", "for_you"])
def test_include_flash_filters_before_pagination_and_composes_with_search_and_my_clubs(
    client, db, make_user, make_org, token_for, monkeypatch, sort
):
    from app.domains.events import routes as event_routes

    owner = make_user()
    member = make_user()
    club = make_org(owner=owner, name="Fictional Sprint 13 Club")
    boundary = now().replace(microsecond=0)
    db.add(OrgMembership(id=uid(), org_id=club.id, user_id=member.id, role="member", active=True))
    scheduled = [
        _event_record(
            club,
            title=f"Discovery needle scheduled {index:02}",
            starts_at=boundary + timedelta(days=1, minutes=index),
            ends_at=boundary + timedelta(days=1, minutes=index + 30),
            published_at=boundary - timedelta(days=1, minutes=index),
        )
        for index in range(51)
    ]
    flash = _event_record(
        club,
        title="Discovery needle flash",
        starts_at=boundary + timedelta(hours=23),
        ends_at=boundary + timedelta(days=1),
        published_at=boundary - timedelta(minutes=1),
        event_type="flash",
    )
    db.add_all([*scheduled, flash])
    db.commit()
    monkeypatch.setattr(event_routes, "now", lambda: boundary)
    headers = auth(token_for(member))
    common = {"sort": sort, "q": "Discovery needle", "my_clubs": "true", "limit": 50}

    default_page = client.get(EVENTS_URL, params=common, headers=headers)
    filtered_first = client.get(
        EVENTS_URL,
        params={**common, "include_flash": "false"},
        headers=headers,
    )
    filtered_second = client.get(
        EVENTS_URL,
        params={**common, "include_flash": "false", "offset": 50},
        headers=headers,
    )

    assert default_page.status_code == filtered_first.status_code == filtered_second.status_code == 200
    assert flash.id in {item["id"] for item in default_page.json()}
    assert len(filtered_first.json()) == 50
    assert len(filtered_second.json()) == 1
    assert all(item["event_type"] == "scheduled" for item in filtered_first.json())
    assert all(item["event_type"] == "scheduled" for item in filtered_second.json())
    assert len({item["id"] for item in filtered_first.json() + filtered_second.json()}) == 51
    assert client.get(f"{EVENTS_URL}/{flash.id}").json()["event_type"] == "flash"

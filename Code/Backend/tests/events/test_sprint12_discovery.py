from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.discovery import weekly_intervals
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.events.recommendations import (
    for_you_statement,
    matched_reason_codes,
    normalized_profile_tags,
)
from app.domains.events.schemas import EventDraftInput
from app.domains.identity.discovery_models import UserDiscoveryPreferences
from app.domains.organizations.models import OrgMembership


MANILA = ZoneInfo("Asia/Manila")
EVENTS_URL = "/api/v1/events"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _next_date(weekday: int):
    today = now().astimezone(MANILA).date()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


def _at(weekday: int, hour: int, minute: int = 0):
    return datetime.combine(_next_date(weekday), time(hour, minute), tzinfo=MANILA)


def _event_record(org, starts_at, *, title="Fictional campus gathering", event_id=None, ends_at=None):
    return Event(
        id=event_id or uid(),
        org_id=org.id,
        created_by=org.created_by,
        title=title,
        summary="",
        description="A fictional local demonstration.",
        starts_at=starts_at,
        ends_at=ends_at or starts_at + timedelta(hours=2),
        venue_name="PLM courtyard",
        venue_address="Intramuros, Manila",
        capacity=3,
        banner_key="heritage",
        cost_label="Free",
        status="published",
        registration_mode="instant",
        event_type="scheduled",
        tags=[],
        coarse_area=None,
        published_at=now(),
        material_revision=0,
        next_admission=0,
        interest_count=0,
    )


def test_draft_metadata_normalizes_validates_and_changes_draft_version(
    client, make_user, make_org, token_for
):
    payload = EventDraftInput.model_validate(
        {"tags": ["  ＡRTS ", "arts", "Straße"], "coarse_area": "  Ｉntramuros "}
    )
    assert payload.tags == ["arts", "strasse"]
    assert payload.coarse_area == "intramuros"
    assert EventDraftInput.model_validate({"coarse_area": "   "}).coarse_area is None

    with pytest.raises(ValidationError):
        EventDraftInput.model_validate({"tags": [["nested"]]})
    with pytest.raises(ValidationError):
        EventDraftInput.model_validate({"tags": ["ß" * 33]})
    with pytest.raises(ValidationError):
        EventDraftInput.model_validate({"coarse_area": "ß" * 41})
    defaults = EventDraftInput.model_validate({})
    assert defaults.tags == [] and defaults.coarse_area is None

    schema = EventDraftInput.model_json_schema()["properties"]
    assert schema["tags"]["maxItems"] == 16
    assert schema["tags"]["items"]["maxLength"] == 64
    area_schema = schema["coarse_area"]
    area_string_schema = next(option for option in area_schema["anyOf"] if option["type"] == "string")
    assert area_string_schema["maxLength"] == 80

    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="pending")
    headers = auth(token_for(owner))
    created = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={"tags": ["  ＡRTS ", "arts", "Straße"], "coarse_area": "  Ｉntramuros "},
        headers=headers,
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["tags"] == ["arts", "strasse"]
    assert draft["coarse_area"] == "intramuros"
    assert draft["recommendation_reasons"] == []

    changed = client.patch(
        f"/api/v1/events/{draft['id']}/draft",
        json={"coarse_area": "Quezon City"},
        headers={**headers, "If-Match": f'"{draft["draft_version"]}"'},
    )
    assert changed.status_code == 200
    assert changed.json()["coarse_area"] == "quezon city"
    assert changed.json()["draft_version"] != draft["draft_version"]
    invalid_nested = client.patch(
        f"/api/v1/events/{draft['id']}/draft",
        json={"tags": [["nested"]]},
        headers=headers,
    )
    assert invalid_nested.status_code == 422

    approved_org = make_org(owner=owner)
    starts_at = now() + timedelta(days=3)
    complete_without_metadata = client.post(
        f"/api/v1/organizations/{approved_org.id}/events",
        json={
            "title": "Optional discovery metadata",
            "description": "A fictional local demonstration.",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=2)).isoformat(),
            "venue_name": "PLM courtyard",
            "venue_address": "Intramuros, Manila",
            "capacity": 8,
            "banner_key": "heritage",
        },
        headers=headers,
    )
    assert complete_without_metadata.status_code == 201
    untagged_draft = complete_without_metadata.json()
    assert untagged_draft["tags"] == [] and untagged_draft["coarse_area"] is None
    published = client.post(
        f"/api/v1/events/{untagged_draft['id']}/publish",
        headers={**headers, "If-Match": f'"{untagged_draft["draft_version"]}"'},
    )
    assert published.status_code == 200
    assert published.json()["tags"] == [] and published.json()["coarse_area"] is None
    assert published.json()["recommendation_reasons"] == []
    immutable_metadata = client.post(
        f"/api/v1/events/{untagged_draft['id']}/changes",
        json={"tags": ["arts"], "reconfirm_deadline": (starts_at - timedelta(hours=1)).isoformat()},
        headers=headers,
    )
    assert immutable_metadata.status_code == 422


def test_profile_tags_normalize_and_deduplicate_before_matching():
    assert normalized_profile_tags([" Arts ", "arts", "Straße", "STRASSE", "   "]) == {
        "arts",
        "strasse",
    }
    assert matched_reason_codes(1, 2, 1, 1) == [
        "club",
        "interests",
        "area",
        "availability",
    ]
    assert matched_reason_codes(0, 0, 0, 0) == []


def test_for_you_ranks_lexicographically_and_composes_search_and_my_clubs(
    client, db, make_user, make_org, make_event, token_for
):
    member = make_user(tags=[" Arts ", "MUSIC", "arts", "Private Profile Topic"])
    club = make_org(name="Fictional Arts Club")
    outside = make_org(name="Fictional Outside Club")
    db.add(OrgMembership(id=uid(), org_id=club.id, user_id=member.id, role="member", active=True))
    db.commit()
    db.add(
        UserDiscoveryPreferences(
            user_id=member.id,
            coarse_area="intramuros",
            availability=[{"weekday": 0, "start_minute": 540, "end_minute": 780}],
        )
    )
    db.commit()

    club_match = make_event(
        org=club,
        title="Chosen club gathering",
        starts_at=_at(2, 11),
        ends_at=_at(2, 12),
        tags=[],
    )
    club_earlier = make_event(
        org=club,
        title="Another club gathering",
        starts_at=_at(2, 10),
        ends_at=_at(2, 11),
        tags=[],
    )
    interest_two = make_event(
        org=outside,
        title="Two interests",
        starts_at=_at(1, 10),
        ends_at=_at(1, 11),
        tags=["arts", "music", "arts"],
    )
    interest_area_availability = make_event(
        org=outside,
        title="One interest, area and time",
        starts_at=_at(0, 10),
        ends_at=_at(0, 11),
        tags=["arts", "arts"],
        coarse_area="intramuros",
    )
    area_only = make_event(
        org=outside,
        title="Area only",
        starts_at=_at(1, 9),
        ends_at=_at(1, 10),
        tags=[],
        coarse_area="intramuros",
    )
    availability_only = make_event(
        org=outside,
        title="Availability only",
        starts_at=_at(0, 9, 30),
        ends_at=_at(0, 10, 30),
        tags=[],
    )
    tie_later = make_event(
        org=outside,
        id="00000000-0000-0000-0000-000000000002",
        title="No match later id",
        starts_at=_at(2, 13),
        ends_at=_at(2, 14),
        tags=[],
    )
    tie_earlier = make_event(
        org=outside,
        id="00000000-0000-0000-0000-000000000001",
        title="No match earlier id",
        starts_at=_at(2, 13),
        ends_at=_at(2, 14),
        tags=[],
    )

    headers = auth(token_for(member))
    response = client.get(EVENTS_URL, params={"sort": "for_you"}, headers=headers)
    assert response.status_code == 200
    cards = response.json()
    assert [card["id"] for card in cards] == [
        club_earlier.id,
        club_match.id,
        interest_two.id,
        interest_area_availability.id,
        area_only.id,
        availability_only.id,
        tie_earlier.id,
        tie_later.id,
    ]
    reasons = {card["id"]: card["recommendation_reasons"] for card in cards}
    assert reasons[club_earlier.id] == ["club"]
    assert reasons[club_match.id] == ["club"]
    assert reasons[interest_two.id] == ["interests"]
    assert reasons[interest_area_availability.id] == ["interests", "area", "availability"]
    assert reasons[area_only.id] == ["area"]
    assert reasons[availability_only.id] == ["availability"]
    assert reasons[tie_earlier.id] == reasons[tie_later.id] == []
    assert "Private Profile Topic" not in response.text
    assert all("availability" not in card for card in cards)
    matched_card = next(card for card in cards if card["id"] == interest_area_availability.id)
    assert matched_card["tags"] == ["arts", "arts"]
    assert matched_card["coarse_area"] == "intramuros"
    detail = client.get(f"{EVENTS_URL}/{interest_area_availability.id}")
    assert detail.status_code == 200
    assert detail.json()["recommendation_reasons"] == []
    assert response.headers["cache-control"] == "private, no-store"
    assert "authorization" in {part.strip().casefold() for part in response.headers["vary"].split(",")}

    composed = client.get(
        EVENTS_URL,
        params={"sort": "for_you", "my_clubs": "true", "q": "Chosen"},
        headers=headers,
    )
    assert composed.status_code == 200
    assert [card["id"] for card in composed.json()] == [club_match.id]


def test_interest_sql_counts_distinct_event_tag_values(db, make_event):
    event = make_event(tags=["arts", "arts", "music", "music"])
    row = db.execute(
        for_you_statement(
            select(Event.id).where(Event.id == event.id),
            active_clubs=[],
            profile_tags={"arts", "music"},
            coarse_area=None,
            availability=[],
        )
    ).one()
    assert row[0] == event.id
    assert row[2] == 2


def test_availability_requires_whole_event_and_handles_week_wrap_and_full_week(
    client, db, make_user, make_org, make_event, token_for
):
    member = make_user(tags=[])
    organization = make_org()
    db.add(
        UserDiscoveryPreferences(
            user_id=member.id,
            coarse_area=None,
            availability=[
                {"weekday": 6, "start_minute": 1380, "end_minute": 1440},
                {"weekday": 0, "start_minute": 0, "end_minute": 60},
            ],
        )
    )
    db.commit()

    sunday_start = datetime.combine(_next_date(6), time(23, 30), tzinfo=MANILA)
    wrapped_fit = make_event(
        org=organization,
        title="Sunday to Monday within window",
        starts_at=sunday_start,
        ends_at=sunday_start + timedelta(hours=1),
        tags=[],
    )
    wrapped_overrun = make_event(
        org=organization,
        title="Sunday to Monday past window",
        starts_at=sunday_start,
        ends_at=sunday_start + timedelta(hours=2),
        tags=[],
    )
    multweek_start = _at(0, 9)
    multweek = make_event(
        org=organization,
        title="Long event",
        starts_at=multweek_start,
        ends_at=multweek_start + timedelta(days=8),
        tags=[],
    )

    response = client.get(EVENTS_URL, params={"sort": "for_you"}, headers=auth(token_for(member)))
    assert response.status_code == 200
    reasons = {card["id"]: card["recommendation_reasons"] for card in response.json()}
    assert reasons[wrapped_fit.id] == ["availability"]
    assert reasons[wrapped_overrun.id] == []
    assert reasons[multweek.id] == []

    full_week = [{"weekday": weekday, "start_minute": 0, "end_minute": 1440} for weekday in range(7)]
    preferences = db.get(UserDiscoveryPreferences, member.id)
    preferences.availability = full_week
    db.commit()
    full_week_response = client.get(
        EVENTS_URL, params={"sort": "for_you"}, headers=auth(token_for(member))
    )
    full_week_reasons = {
        card["id"]: card["recommendation_reasons"] for card in full_week_response.json()
    }
    assert full_week_reasons[multweek.id] == ["availability"]

    with pytest.raises(ValidationError):
        weekly_intervals([{"weekday": True, "start_minute": 0, "end_minute": 30}])


def test_for_you_paginates_after_global_ranking_over_more_than_fifty_events(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    club = make_org(owner=owner)
    outside = make_org()
    member = make_user()
    db.add(OrgMembership(id=uid(), org_id=club.id, user_id=member.id, role="member", active=True))
    db.commit()

    base = now() + timedelta(days=2)
    rows = [
        _event_record(outside, base + timedelta(minutes=index), title=f"Fictional event {index:02}")
        for index in range(51)
    ]
    club_event = _event_record(
        club,
        base + timedelta(days=4),
        title="Club event after chronological page",
    )
    db.add_all([*rows, club_event])
    db.commit()

    headers = auth(token_for(member))
    first_page = client.get(EVENTS_URL, params={"sort": "for_you", "limit": 50}, headers=headers)
    second_page = client.get(
        EVENTS_URL,
        params={"sort": "for_you", "limit": 50, "offset": 50},
        headers=headers,
    )
    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()[0]["id"] == club_event.id
    assert len(first_page.json()) == 50
    assert len(second_page.json()) == 2
    assert len({card["id"] for card in first_page.json() + second_page.json()}) == 52


def test_guest_and_chronological_projections_have_no_recommendation_reasons(
    client, make_event
):
    later = make_event(starts_at=now() + timedelta(days=4), ends_at=now() + timedelta(days=4, hours=1))
    earlier = make_event(starts_at=now() + timedelta(days=2), ends_at=now() + timedelta(days=2, hours=1))

    guest_for_you = client.get(EVENTS_URL, params={"sort": "for_you"})
    explicit_upcoming = client.get(EVENTS_URL, params={"sort": "upcoming"})
    detail = client.get(f"{EVENTS_URL}/{earlier.id}")
    assert guest_for_you.status_code == explicit_upcoming.status_code == detail.status_code == 200
    assert [card["id"] for card in guest_for_you.json()] == [earlier.id, later.id]
    assert all(card["recommendation_reasons"] == [] for card in guest_for_you.json())
    assert all(card["recommendation_reasons"] == [] for card in explicit_upcoming.json())
    assert detail.json()["recommendation_reasons"] == []
    assert detail.json()["tags"] == []
    assert detail.json()["coarse_area"] is None


def test_ineligible_actor_does_not_receive_club_match_reason(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    ineligible = make_user(email="fictional-ineligible@example.test", tags=[])
    db.add(
        OrgMembership(
            id=uid(), org_id=organization.id, user_id=ineligible.id, role="member", active=True
        )
    )
    db.commit()
    event = make_event(org=organization, tags=[])

    response = client.get(
        EVENTS_URL,
        params={"sort": "for_you"},
        headers=auth(token_for(ineligible)),
    )
    assert response.status_code == 200
    card = next(item for item in response.json() if item["id"] == event.id)
    assert card["recommendation_reasons"] == []

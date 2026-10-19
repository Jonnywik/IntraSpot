from datetime import datetime, timedelta, timezone, tzinfo

import pytest
from pydantic import ValidationError

from app.core.errors import DomainError
from app.db.models import now
from app.db.session import session_factory
from app.domains.events.models import Event
from app.domains.events.schemas import EventChangeInput, EventDraftInput
from app.domains.events.service import validate_material_change, validate_publishable


POSTGRES_INTEGER_MAX = 2_147_483_647


class _RepeatedHourTimezone(tzinfo):
    def utcoffset(self, value):
        return timedelta(hours=-5 if value is not None and value.fold else -4)

    def dst(self, value):
        return timedelta(0) if value is not None and value.fold else timedelta(hours=1)


def _publishable_event(**overrides) -> Event:
    starts_at = now() + timedelta(days=2)
    fields = {
        "id": "event-id",
        "org_id": "organization-id",
        "created_by": "user-id",
        "title": "Fictional local event",
        "summary": "",
        "description": "A fictional event description.",
        "starts_at": starts_at,
        "ends_at": starts_at + timedelta(hours=2),
        "venue_name": "Fictional venue",
        "venue_address": "Fictional address",
        "capacity": 1,
        "banner_key": "heritage",
        "cost_label": "Free",
        "status": "draft",
        "registration_mode": "instant",
        "review_window_minutes": None,
        "material_revision": 0,
        "event_type": "scheduled",
        "published_at": None,
    }
    return Event(**(fields | overrides))


def test_capacity_is_bounded_by_postgres_integer_storage():
    assert EventDraftInput(capacity=POSTGRES_INTEGER_MAX).capacity == POSTGRES_INTEGER_MAX

    with pytest.raises(ValidationError):
        EventDraftInput(capacity=POSTGRES_INTEGER_MAX + 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [("event_type", "unrecognized")],
)
def test_draft_schema_rejects_unknown_event_modes(field, value):
    with pytest.raises(ValidationError):
        EventDraftInput.model_validate({field: value})


def test_approval_drafts_may_be_incomplete_but_publication_requires_a_valid_window():
    incomplete = EventDraftInput(registration_mode="approval")
    assert incomplete.review_window_minutes is None

    with pytest.raises(DomainError) as missing_window:
        validate_publishable(_publishable_event(registration_mode="approval"))
    assert missing_window.value.code == "event_review_window_invalid"

    for minutes in (15, 2880):
        validate_publishable(
            _publishable_event(
                registration_mode="approval",
                review_window_minutes=minutes,
            )
        )

    for minutes in (14, 2881):
        with pytest.raises(ValidationError):
            EventDraftInput.model_validate(
                {"registration_mode": "approval", "review_window_minutes": minutes}
            )


def test_material_change_input_is_explicit_and_defaults_to_exact_selection():
    starts_at = now() + timedelta(days=3)
    payload = EventChangeInput(
        starts_at=starts_at,
        reconfirm_deadline=now() + timedelta(days=1),
    )

    assert payload.selection_mode == "exact"
    assert payload.selected_registration_ids == []

    with pytest.raises(ValidationError):
        EventChangeInput.model_validate(
            {
                "starts_at": starts_at,
                "reconfirm_deadline": now() + timedelta(days=1),
                "registration_mode": "approval",
            }
        )


def test_material_change_validates_merged_event_and_deadline_without_mutating_event():
    event = _publishable_event(status="published")
    original_start = event.starts_at
    new_start = original_start + timedelta(hours=1)
    deadline = now() + timedelta(days=1)

    proposed = validate_material_change(
        event,
        {"starts_at": new_start},
        deadline,
        at=now(),
    )

    assert proposed["starts_at"] == new_start
    assert proposed["ends_at"] == event.ends_at
    assert set(proposed) == {
        "starts_at", "ends_at", "venue_name", "venue_address", "capacity", "cost_label"
    }
    assert event.starts_at == original_start

    with pytest.raises(DomainError) as invalid_deadline:
        validate_material_change(
            event,
            {"starts_at": new_start},
            new_start,
            at=now(),
        )
    assert invalid_deadline.value.code == "event_reconfirmation_deadline_invalid"


@pytest.mark.parametrize("field", ["title", "description", "venue_name", "venue_address"])
@pytest.mark.parametrize("blank", ["", " \t\r\n"])
def test_publish_rejects_blank_required_text(field, blank):
    with pytest.raises(DomainError) as error:
        validate_publishable(_publishable_event(**{field: blank}))

    assert error.value.code == "event_fields_required"


def test_publish_compares_times_as_utc_instants_across_a_dst_fold():
    repeated_hour = _RepeatedHourTimezone()
    starts_at = datetime(2020, 11, 1, 1, 50, tzinfo=repeated_hour, fold=0)
    ends_at = datetime(2020, 11, 1, 1, 10, tzinfo=repeated_hour, fold=1)
    at = datetime(2020, 10, 31, 12, tzinfo=timezone.utc)
    assert ends_at.astimezone(timezone.utc) > starts_at.astimezone(timezone.utc)

    validate_publishable(_publishable_event(starts_at=starts_at, ends_at=ends_at), at=at)


def test_cost_label_is_informational_for_publishing():
    validate_publishable(_publishable_event(cost_label="Pay the organization at the venue"))


def test_offset_aware_draft_times_round_trip_as_the_same_utc_instants(
    client, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/events",
        json={
            "starts_at": "2031-02-03T12:30:00+05:30",
            "ends_at": "2031-02-03T03:00:00-05:00",
        },
        headers={"Authorization": f"Bearer {token_for(owner)}"},
    )
    assert response.status_code == 201

    with session_factory()() as verification_db:
        stored = verification_db.get(Event, response.json()["id"])

    assert stored is not None
    assert stored.starts_at is not None and stored.starts_at.utcoffset() is not None
    assert stored.ends_at is not None and stored.ends_at.utcoffset() is not None
    expected_start = datetime(2031, 2, 3, 7, tzinfo=timezone.utc)
    expected_end = datetime(2031, 2, 3, 8, tzinfo=timezone.utc)
    assert stored.starts_at.astimezone(timezone.utc) == expected_start
    assert stored.ends_at.astimezone(timezone.utc) == expected_end

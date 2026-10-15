from datetime import datetime, timedelta, timezone

import pytest

from app.domains.events import routes as event_routes
from app.domains.registrations import service as registration_service


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_active_discovery_includes_ongoing_but_excludes_exact_end_boundary(
    client, make_event, monkeypatch
):
    manila = timezone(timedelta(hours=8))
    boundary = datetime(2027, 1, 1, 16, 30, tzinfo=timezone.utc)
    ongoing = make_event(
        title="Already started, still active",
        starts_at=datetime(2027, 1, 2, 0, 0, tzinfo=manila),
        ends_at=datetime(2027, 1, 2, 2, 0, tzinfo=manila),
    )
    ending_at_boundary = make_event(
        title="Ended exactly now",
        starts_at=datetime(2027, 1, 2, 0, 0, tzinfo=manila),
        ends_at=datetime(2027, 1, 2, 0, 30, tzinfo=manila),
    )
    # Sprint 4: discovery uses the app now() clock (Python boundary), not DB
    # func.now(). Freeze that single clock source; assertions unchanged.
    monkeypatch.setattr(event_routes, "now", lambda: boundary)

    response = client.get("/api/v1/events")

    assert response.status_code == 200
    discovered_ids = {item["id"] for item in response.json()}
    assert discovered_ids == {ongoing.id}
    assert ending_at_boundary.id not in discovered_ids


@pytest.mark.parametrize(
    "now_after_start",
    [timedelta(0), timedelta(seconds=1)],
    ids=("at-start", "one-second-after"),
)
def test_registration_at_or_after_start_is_denied_across_utc_date_rollover(
    client, make_event, make_user, token_for, monkeypatch, now_after_start
):
    manila = timezone(timedelta(hours=8))
    starts_at = datetime(2027, 1, 2, 0, 30, tzinfo=manila)
    boundary = starts_at.astimezone(timezone.utc) + now_after_start
    event = make_event(
        starts_at=starts_at,
        ends_at=datetime(2027, 1, 2, 2, 30, tzinfo=manila),
    )
    attendee = make_user()
    monkeypatch.setattr(registration_service, "now", lambda: boundary)

    response = client.post(
        f"/api/v1/events/{event.id}/registrations",
        headers=auth(token_for(attendee)) | {"Idempotency-Key": "at-start-rollover"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "event_started"


def test_malformed_event_paths_return_sanitized_errors_without_event_data(
    client, make_event
):
    private_title = "PRIVATE_LIFECYCLE_ROUTE_MARKER"
    event = make_event(title=private_title)
    malformed_id = "malformed-event-id-DO-NOT-ECHO"

    malformed_detail = client.get(f"/api/v1/events/{malformed_id}")
    unknown_nested_route = client.get(f"/api/v1/events/{event.id}/draft/extra")

    assert malformed_detail.status_code == 422
    assert malformed_detail.json()["error"]["code"] == "validation_error"
    assert unknown_nested_route.status_code == 404
    assert unknown_nested_route.json()["error"]["code"] == "http_error"
    for response in (malformed_detail, unknown_nested_route):
        assert malformed_id not in response.text
        assert event.id not in response.text
        assert private_title not in response.text

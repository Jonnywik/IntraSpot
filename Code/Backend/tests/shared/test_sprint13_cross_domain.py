from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import now
from app.domains.events.models import Event
from app.domains.registrations import service as registration_service
from app.domains.registrations.models import Registration, RegistrationReceipt


EVENTS_URL = "/api/v1/events"
PREFERENCES_URL = "/api/v1/me/preferences"
MY_REGISTRATIONS_URL = "/api/v1/me/registrations"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _my_registration(client, token, event_id):
    response = client.get(MY_REGISTRATIONS_URL, headers=auth(token))
    assert response.status_code == 200
    return next(item for item in response.json() if item["event_id"] == event_id)


def test_hidden_flash_stays_registered_and_waitlist_promotion_keeps_chat_access(
    client, db, make_event, make_user, token_for
):
    boundary = now().replace(microsecond=0)
    event = make_event(
        title="Fictional Sprint 13 cross-domain Flash",
        description="A fictional event used only for isolated QA.",
        starts_at=boundary + timedelta(hours=6),
        ends_at=boundary + timedelta(hours=7),
        published_at=boundary - timedelta(minutes=30),
        capacity=1,
        registration_mode="instant",
        review_window_minutes=None,
        event_type="flash",
    )
    confirmed_user = make_user()
    waitlisted_user = make_user()
    db.commit()

    confirmed = registration_service.submit_registration(
        confirmed_user.id, event.id, "s13-flash-confirmed-01"
    )
    confirmed_retry = registration_service.submit_registration(
        confirmed_user.id, event.id, "s13-flash-confirmed-01"
    )
    waitlisted = registration_service.submit_registration(
        waitlisted_user.id, event.id, "s13-flash-waitlisted-01"
    )

    assert confirmed.http_status == confirmed_retry.http_status == 201
    assert confirmed_retry.result == confirmed.result
    assert confirmed.result["status"] == "confirmed"
    assert waitlisted.http_status == 201
    assert waitlisted.result["status"] == "waitlisted"

    confirmed_token = token_for(confirmed_user)
    waitlisted_token = token_for(waitlisted_user)
    for token in (confirmed_token, waitlisted_token):
        saved = client.patch(
            PREFERENCES_URL,
            json={"show_flash": False},
            headers=auth(token),
        )
        assert saved.status_code == 200
        assert saved.json()["show_flash"] is False

    default_feed = client.get(EVENTS_URL)
    hidden_feed = client.get(EVENTS_URL, params={"include_flash": False})
    detail = client.get(f"{EVENTS_URL}/{event.id}")
    assert default_feed.status_code == hidden_feed.status_code == detail.status_code == 200
    assert event.id in {item["id"] for item in default_feed.json()}
    assert event.id not in {item["id"] for item in hidden_feed.json()}
    assert detail.json()["event_type"] == "flash"

    assert _my_registration(client, confirmed_token, event.id)["status"] == "confirmed"
    assert _my_registration(client, waitlisted_token, event.id)["status"] == "waitlisted"
    confirmed_chat = client.get(
        f"{EVENTS_URL}/{event.id}/chat", headers=auth(confirmed_token)
    )
    waitlisted_chat = client.get(
        f"{EVENTS_URL}/{event.id}/chat", headers=auth(waitlisted_token)
    )
    assert confirmed_chat.status_code == 200
    assert waitlisted_chat.status_code == 403
    assert waitlisted_chat.json()["error"]["code"] == "chat_access_forbidden"

    cancelled = registration_service.withdraw_registration(confirmed_user.id, event.id)
    assert cancelled["status"] == "cancelled"
    db.expire_all()
    assert _my_registration(client, confirmed_token, event.id)["status"] == "cancelled"
    promoted = _my_registration(client, waitlisted_token, event.id)
    assert promoted["status"] == "confirmed"
    assert client.get(
        f"{EVENTS_URL}/{event.id}/chat", headers=auth(waitlisted_token)
    ).status_code == 200

    replay = registration_service.submit_registration(
        waitlisted_user.id, event.id, "s13-flash-waitlisted-01"
    )
    assert replay.http_status == waitlisted.http_status
    assert replay.result == waitlisted.result

    db.expire_all()
    assert db.scalar(select(Event.next_admission).where(Event.id == event.id)) == 2
    assert db.scalar(
        select(func.count(Registration.id)).where(Registration.event_id == event.id)
    ) == 2
    assert db.scalar(
        select(func.count(RegistrationReceipt.id)).where(
            RegistrationReceipt.event_id == event.id
        )
    ) == 2

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.domains.identity.discovery import _upsert_discovery_preferences
from app.domains.identity.discovery_models import UserDiscoveryPreferences


DISCOVERY_PREFERENCES_URL = "/api/v1/me/discovery-preferences"
WINDOW = {"weekday": 0, "start_minute": 540, "end_minute": 660}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_utc_timestamp(value: str) -> None:
    assert datetime.fromisoformat(value).utcoffset().total_seconds() == 0


def assert_private_headers(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert "authorization" in {
        value.strip().casefold() for value in response.headers["vary"].split(",")
    }


def test_get_returns_private_defaults_without_creating_a_row(client, db, make_user, token_for):
    user = make_user(email="fictional@example.test", email_verified=True)

    response = client.get(DISCOVERY_PREFERENCES_URL, headers=bearer(token_for(user)))

    assert response.status_code == 200
    assert response.json() == {"coarse_area": None, "availability": [], "updated_at": None}
    assert_private_headers(response)
    assert db.get(UserDiscoveryPreferences, user.id) is None


def test_preferences_are_account_scoped_and_response_omits_account_identity(
    client, db, make_user, token_for
):
    first = make_user(email="first@example.test", email_verified=True)
    second = make_user(email="second@example.test", email_verified=True)
    first_headers = bearer(token_for(first))
    second_headers = bearer(token_for(second))

    updated = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=first_headers,
        json={"coarse_area": "North Campus", "availability": [WINDOW]},
    )
    first_read = client.get(DISCOVERY_PREFERENCES_URL, headers=first_headers)
    second_read = client.get(DISCOVERY_PREFERENCES_URL, headers=second_headers)
    forged = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=first_headers,
        json={"user_id": second.id, "coarse_area": "Other area"},
    )

    assert updated.status_code == first_read.status_code == second_read.status_code == 200
    assert first_read.json()["coarse_area"] == "north campus"
    assert first_read.json()["availability"] == [WINDOW]
    assert set(first_read.json()) == {"coarse_area", "availability", "updated_at"}
    assert "email" not in first_read.json()
    assert second_read.json() == {"coarse_area": None, "availability": [], "updated_at": None}
    assert db.get(UserDiscoveryPreferences, second.id) is None
    assert forged.status_code == 422
    assert_private_headers(updated)
    assert_private_headers(first_read)
    assert_private_headers(second_read)
    assert_utc_timestamp(updated.json()["updated_at"])


def test_patch_is_partial_and_explicit_clear_values_preserve_omitted_fields(
    client, make_user, token_for
):
    user = make_user()
    headers = bearer(token_for(user))

    initial = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=headers,
        json={"coarse_area": "Library", "availability": [WINDOW]},
    )
    clear_area = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=headers,
        json={"coarse_area": None},
    )
    clear_windows = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=headers,
        json={"availability": []},
    )

    assert initial.status_code == clear_area.status_code == clear_windows.status_code == 200
    assert clear_area.json()["coarse_area"] is None
    assert clear_area.json()["availability"] == [WINDOW]
    assert clear_windows.json()["coarse_area"] is None
    assert clear_windows.json()["availability"] == []
    for response in (initial, clear_area, clear_windows):
        assert_private_headers(response)
        assert_utc_timestamp(response.json()["updated_at"])


def test_empty_patch_is_a_read_only_noop(client, db, make_user, token_for):
    user = make_user()
    headers = bearer(token_for(user))

    missing = client.patch(DISCOVERY_PREFERENCES_URL, headers=headers, json={})
    assert missing.status_code == 200
    assert missing.json() == {"coarse_area": None, "availability": [], "updated_at": None}
    assert db.get(UserDiscoveryPreferences, user.id) is None

    written = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=headers,
        json={"coarse_area": "Auditorium", "availability": [WINDOW]},
    )
    empty = client.patch(DISCOVERY_PREFERENCES_URL, headers=headers, json={})

    assert written.status_code == empty.status_code == 200
    assert empty.json()["coarse_area"] == "auditorium"
    assert empty.json()["availability"] == [WINDOW]
    assert empty.json()["updated_at"] == written.json()["updated_at"]
    assert_private_headers(missing)
    assert_private_headers(written)
    assert_private_headers(empty)
    assert db.scalar(
        select(func.count())
        .select_from(UserDiscoveryPreferences)
        .where(UserDiscoveryPreferences.user_id == user.id)
    ) == 1


def test_area_normalizes_nfkc_whitespace_and_casefold_before_persisting(client, make_user, token_for):
    user = make_user()

    response = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=bearer(token_for(user)),
        json={"coarse_area": "  Ｍain Straße　 Campus  "},
    )

    assert response.status_code == 200
    assert response.json()["coarse_area"] == "main strasse campus"


def test_blank_area_clears_and_an_80_character_normalized_area_is_accepted(
    client, make_user, token_for
):
    user = make_user()
    headers = bearer(token_for(user))
    client.patch(DISCOVERY_PREFERENCES_URL, headers=headers, json={"coarse_area": "Hall"})

    cleared = client.patch(DISCOVERY_PREFERENCES_URL, headers=headers, json={"coarse_area": " 　"})
    boundary = client.patch(DISCOVERY_PREFERENCES_URL, headers=headers, json={"coarse_area": "A" * 80})

    assert cleared.status_code == boundary.status_code == 200
    assert cleared.json()["coarse_area"] is None
    assert boundary.json()["coarse_area"] == "a" * 80


def test_area_rejects_oversize_raw_and_normalized_values_before_persistence(
    client, db, make_user, token_for
):
    user = make_user()
    headers = bearer(token_for(user))

    raw_oversize = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=headers,
        json={"coarse_area": "x" * 501},
    )
    normalization_expansion = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=headers,
        json={"coarse_area": "ﬃ" * 27},
    )

    assert raw_oversize.status_code == normalization_expansion.status_code == 422
    assert db.get(UserDiscoveryPreferences, user.id) is None


@pytest.mark.parametrize(
    "body",
    [
        {"unknown": True},
        {"coarse_area": 123},
        {"availability": None},
        {"availability": [WINDOW] * 29},
        {"availability": [{"weekday": -1, "start_minute": 10, "end_minute": 20}]},
        {"availability": [{"weekday": 7, "start_minute": 10, "end_minute": 20}]},
        {"availability": [{"weekday": 0, "start_minute": -1, "end_minute": 20}]},
        {"availability": [{"weekday": 0, "start_minute": 1440, "end_minute": 1440}]},
        {"availability": [{"weekday": 0, "start_minute": 10, "end_minute": 0}]},
        {"availability": [{"weekday": 0, "start_minute": 10, "end_minute": 1441}]},
        {"availability": [{"weekday": 0, "start_minute": 60, "end_minute": 60}]},
        {"availability": [{"weekday": 0, "start_minute": 90, "end_minute": 60}]},
        {"availability": [{"weekday": True, "start_minute": 10, "end_minute": 20}]},
        {"availability": [{"weekday": 0, "start_minute": False, "end_minute": 20}]},
        {"availability": [{"weekday": 0, "start_minute": 10, "end_minute": True}]},
        {"availability": [{**WINDOW, "unexpected": "field"}]},
    ],
)
def test_patch_rejects_unknown_wrong_type_oversize_and_invalid_windows(
    client, db, make_user, token_for, body
):
    user = make_user()

    response = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=bearer(token_for(user)),
        json=body,
    )

    assert response.status_code == 422
    assert db.get(UserDiscoveryPreferences, user.id) is None


def test_patch_preserves_all_28_availability_rows_as_submitted(client, make_user, token_for):
    user = make_user()
    rows = [WINDOW] * 28

    response = client.patch(
        DISCOVERY_PREFERENCES_URL,
        headers=bearer(token_for(user)),
        json={"availability": rows},
    )

    assert response.status_code == 200
    assert response.json()["availability"] == rows


def test_discovery_preferences_require_authentication(client):
    assert client.get(DISCOVERY_PREFERENCES_URL).status_code == 401
    assert client.patch(DISCOVERY_PREFERENCES_URL, json={"coarse_area": "Library"}).status_code == 401


def test_concurrent_partial_upserts_preserve_each_supplied_field(db, make_user):
    user = make_user()
    changes = [{"coarse_area": "north campus"}, {"availability": [WINDOW]}]
    barrier = Barrier(len(changes))

    def apply_patch(patch):
        barrier.wait(timeout=10)
        with Session(engine(), expire_on_commit=False) as session:
            response = _upsert_discovery_preferences(session, user.id, patch)
            session.commit()
            return response

    with ThreadPoolExecutor(max_workers=len(changes)) as executor:
        results = list(executor.map(apply_patch, changes))

    db.expire_all()
    row = db.get(UserDiscoveryPreferences, user.id)
    assert len(results) == len(changes)
    assert row is not None
    assert row.coarse_area == "north campus"
    assert row.availability == [WINDOW]
    assert db.scalar(
        select(func.count())
        .select_from(UserDiscoveryPreferences)
        .where(UserDiscoveryPreferences.user_id == user.id)
    ) == 1

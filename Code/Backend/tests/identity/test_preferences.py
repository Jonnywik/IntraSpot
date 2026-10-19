from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.domains.identity.preferences import _upsert_preferences
from app.domains.identity.preferences_models import UserPreferences


PREFERENCES_URL = "/api/v1/me/preferences"
DEFAULTS = {
    "language": "en",
    "theme": "light",
    "text_size": "standard",
    "high_contrast": False,
    "reduced_motion": False,
    "decoration_paused": False,
    "show_flash": True,
}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_utc_timestamp(value: str) -> None:
    assert datetime.fromisoformat(value).utcoffset().total_seconds() == 0


def test_get_returns_defaults_without_creating_a_row(client, db, make_user, token_for):
    user = make_user()

    response = client.get(PREFERENCES_URL, headers=bearer(token_for(user)))

    assert response.status_code == 200
    assert response.json() == DEFAULTS | {"initialized": False, "updated_at": None}
    assert db.get(UserPreferences, user.id) is None


def test_preferences_are_isolated_per_authenticated_account(client, make_user, token_for):
    first = make_user(email="first@students.plm.edu.ph")
    second = make_user(email="second@students.plm.edu.ph")

    first_update = client.patch(
        PREFERENCES_URL,
        headers=bearer(token_for(first)),
        json={"language": "fil", "theme": "dark"},
    )
    second_update = client.patch(
        PREFERENCES_URL,
        headers=bearer(token_for(second)),
        json={"text_size": "large"},
    )
    first_read = client.get(PREFERENCES_URL, headers=bearer(token_for(first)))
    second_read = client.get(PREFERENCES_URL, headers=bearer(token_for(second)))

    assert first_update.status_code == second_update.status_code == 200
    assert first_read.status_code == second_read.status_code == 200
    first_body = first_read.json()
    second_body = second_read.json()
    first_updated_at = first_body.pop("updated_at")
    second_updated_at = second_body.pop("updated_at")
    assert first_body == DEFAULTS | {
        "language": "fil",
        "theme": "dark",
        "initialized": True,
    }
    assert second_body == DEFAULTS | {
        "text_size": "large",
        "initialized": True,
    }
    assert_utc_timestamp(first_updated_at)
    assert_utc_timestamp(second_updated_at)
    assert "user_id" not in first_body
    assert "email" not in first_body


def test_ineligible_non_admin_can_read_and_update_preferences(client, make_user, token_for):
    user = make_user(email="fictional@example.test", email_verified=True, platform_admin=False)
    headers = bearer(token_for(user))

    identity = client.get("/api/v1/me", headers=headers)
    read = client.get(PREFERENCES_URL, headers=headers)
    update = client.patch(PREFERENCES_URL, headers=headers, json={"reduced_motion": True})

    assert identity.status_code == 200
    assert identity.json()["eligible"] is False
    assert identity.json()["platform_admin"] is False
    assert identity.json()["grants"] == []
    assert read.status_code == 200
    assert update.status_code == 200
    assert update.json()["reduced_motion"] is True


def test_preferences_require_authentication(client):
    assert client.get(PREFERENCES_URL).status_code == 401
    assert client.patch(PREFERENCES_URL, json={"theme": "dark"}).status_code == 401


@pytest.mark.parametrize(
    "forged_field",
    ["user_id", "email", "email_verified", "active", "platform_admin", "initialized", "updated_at"],
)
def test_patch_rejects_identity_privilege_and_response_fields(
    client, make_user, token_for, forged_field
):
    user = make_user(platform_admin=False, email_verified=False)

    response = client.patch(
        PREFERENCES_URL,
        headers=bearer(token_for(user)),
        json={forged_field: True},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    ["language", "theme", "text_size", "high_contrast", "reduced_motion", "decoration_paused"],
)
def test_patch_rejects_null_values(client, make_user, token_for, field):
    user = make_user()

    response = client.patch(PREFERENCES_URL, headers=bearer(token_for(user)), json={field: None})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("language", "EN"),
        ("language", "es"),
        ("theme", "SYSTEM"),
        ("theme", "automatic"),
        ("text_size", "extra-large"),
        ("text_size", "xlarge"),
    ],
)
def test_patch_rejects_values_outside_each_enum(client, make_user, token_for, field, value):
    user = make_user()

    response = client.patch(PREFERENCES_URL, headers=bearer(token_for(user)), json={field: value})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (field, value)
        for field in ("high_contrast", "reduced_motion", "decoration_paused")
        for value in (0, 1, "false", "true")
    ],
)
def test_patch_rejects_non_boolean_boolean_values(client, make_user, token_for, field, value):
    user = make_user()

    response = client.patch(PREFERENCES_URL, headers=bearer(token_for(user)), json={field: value})

    assert response.status_code == 422


def test_empty_patch_is_a_read_only_noop_for_missing_and_existing_rows(client, db, make_user, token_for):
    user = make_user()
    headers = bearer(token_for(user))

    missing = client.patch(PREFERENCES_URL, headers=headers, json={})
    assert missing.status_code == 200
    assert missing.json() == DEFAULTS | {"initialized": False, "updated_at": None}
    assert db.get(UserPreferences, user.id) is None

    written = client.patch(PREFERENCES_URL, headers=headers, json={"theme": "dark"})
    empty = client.patch(PREFERENCES_URL, headers=headers, json={})

    assert written.status_code == empty.status_code == 200
    assert empty.json()["theme"] == "dark"
    assert empty.json()["initialized"] is True
    assert empty.json()["updated_at"] == written.json()["updated_at"]
    assert db.scalar(
        select(func.count()).select_from(UserPreferences).where(UserPreferences.user_id == user.id)
    ) == 1


def test_partial_patches_preserve_omitted_values(client, make_user, token_for):
    user = make_user()
    headers = bearer(token_for(user))

    first = client.patch(PREFERENCES_URL, headers=headers, json={"language": "fil", "theme": "dark"})
    second = client.patch(PREFERENCES_URL, headers=headers, json={"text_size": "large"})

    assert first.status_code == second.status_code == 200
    body = second.json()
    updated_at = body.pop("updated_at")
    assert body == DEFAULTS | {
        "language": "fil",
        "theme": "dark",
        "text_size": "large",
        "initialized": True,
    }
    assert_utc_timestamp(updated_at)


def test_retried_patch_keeps_one_row_and_the_requested_values(client, db, make_user, token_for):
    user = make_user()
    headers = bearer(token_for(user))
    patch = {"language": "fil", "decoration_paused": True}

    first = client.patch(PREFERENCES_URL, headers=headers, json=patch)
    retry = client.patch(PREFERENCES_URL, headers=headers, json=patch)

    assert first.status_code == retry.status_code == 200
    assert retry.json()["language"] == "fil"
    assert retry.json()["decoration_paused"] is True
    assert db.scalar(
        select(func.count()).select_from(UserPreferences).where(UserPreferences.user_id == user.id)
    ) == 1


def test_concurrent_partial_upserts_preserve_every_supplied_field(db, make_user):
    user = make_user()
    changes = [
        {"language": "fil"},
        {"theme": "dark"},
        {"text_size": "large"},
        {"high_contrast": True},
        {"reduced_motion": True},
        {"decoration_paused": True},
    ]
    barrier = Barrier(len(changes))

    def apply_patch(patch):
        barrier.wait(timeout=10)
        with Session(engine(), expire_on_commit=False) as session:
            response = _upsert_preferences(session, user.id, patch)
            session.commit()
            return response

    with ThreadPoolExecutor(max_workers=len(changes)) as executor:
        results = list(executor.map(apply_patch, changes))

    db.expire_all()
    row = db.get(UserPreferences, user.id)
    assert len(results) == len(changes)
    assert row is not None
    assert row.language == "fil"
    assert row.theme == "dark"
    assert row.text_size == "large"
    assert row.high_contrast is True
    assert row.reduced_motion is True
    assert row.decoration_paused is True
    assert db.scalar(
        select(func.count()).select_from(UserPreferences).where(UserPreferences.user_id == user.id)
    ) == 1

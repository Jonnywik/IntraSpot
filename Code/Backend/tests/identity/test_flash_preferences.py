import pytest


PREFERENCES_URL = "/api/v1/me/preferences"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_private_headers(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert "authorization" in {
        value.strip().casefold() for value in response.headers.get("vary", "").split(",")
    }


def test_show_flash_defaults_to_true_for_an_account_without_saved_preferences(
    client, make_user, token_for
):
    user = make_user()

    response = client.get(PREFERENCES_URL, headers=bearer(token_for(user)))

    assert response.status_code == 200
    assert response.json()["show_flash"] is True
    assert_private_headers(response)


def test_partial_patch_preserves_show_flash_when_older_caller_omits_it(
    client, make_user, token_for
):
    user = make_user()
    headers = bearer(token_for(user))

    hidden = client.patch(PREFERENCES_URL, headers=headers, json={"show_flash": False})
    legacy_patch = client.patch(PREFERENCES_URL, headers=headers, json={"language": "fil"})

    assert hidden.status_code == legacy_patch.status_code == 200
    assert legacy_patch.json()["show_flash"] is False
    assert legacy_patch.json()["language"] == "fil"
    assert_private_headers(hidden)
    assert_private_headers(legacy_patch)


@pytest.mark.parametrize("value", [None, 0, 1, "false", "true"])
def test_patch_rejects_non_boolean_show_flash_values(client, make_user, token_for, value):
    user = make_user()

    response = client.patch(
        PREFERENCES_URL,
        headers=bearer(token_for(user)),
        json={"show_flash": value},
    )

    assert response.status_code == 422


def test_show_flash_is_scoped_to_the_authenticated_account(client, make_user, token_for):
    first = make_user(email="first-flash@example.test")
    second = make_user(email="second-flash@example.test")

    updated = client.patch(
        PREFERENCES_URL,
        headers=bearer(token_for(first)),
        json={"show_flash": False},
    )
    first_read = client.get(PREFERENCES_URL, headers=bearer(token_for(first)))
    second_read = client.get(PREFERENCES_URL, headers=bearer(token_for(second)))

    assert updated.status_code == first_read.status_code == second_read.status_code == 200
    assert first_read.json()["show_flash"] is False
    assert second_read.json()["show_flash"] is True

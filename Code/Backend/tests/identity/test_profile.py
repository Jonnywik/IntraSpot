def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_profile_is_self_only_and_does_not_echo_private_account_fields(client, make_user, token_for):
    first = make_user(nickname="First fictional person", email="first@students.plm.edu.ph")
    make_user(nickname="Second fictional person", email="second@students.plm.edu.ph", persona_visible=True)

    response = client.get("/api/v1/me/profile", headers=bearer(token_for(first)))
    nonexistent_public_profile = client.get(f"/api/v1/users/{first.id}/profile", headers=bearer(token_for(first)))

    assert response.status_code == 200
    assert response.json() == {
        "nickname": "First fictional person",
        "age_bracket": "18-24",
        "tags": ["arts"],
        "pronouns": None,
        "icebreaker": None,
        "persona_visible": False,
    }
    assert "email" not in response.json()
    assert "id" not in response.json()
    assert nonexistent_public_profile.status_code == 404


def test_profile_prerequisites_and_partial_updates(client, make_user, token_for):
    user = make_user(nickname=None, age_bracket=None, tags=[], pronouns="they/them", icebreaker="Hello")
    headers = bearer(token_for(user))

    before = client.get("/api/v1/me", headers=headers)
    updated = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"nickname": "  Fictional attendee  ", "age_bracket": "  18-24  ", "tags": [" art "]},
    )
    after = client.get("/api/v1/me", headers=headers)

    assert before.status_code == 200 and before.json()["profile_complete"] is False
    assert updated.status_code == 200
    assert updated.json() == {
        "nickname": "Fictional attendee",
        "age_bracket": "18-24",
        "tags": ["art"],
        "pronouns": "they/them",
        "icebreaker": "Hello",
        "persona_visible": False,
    }
    assert after.json()["profile_complete"] is True


def test_profile_patch_cannot_elevate_or_change_account_identity(client, db, make_user, token_for):
    user = make_user(platform_admin=False, email_verified=False, email="fictional@example.test")

    response = client.patch(
        "/api/v1/me/profile",
        headers=bearer(token_for(user)),
        json={"nickname": "Updated", "platform_admin": True, "email_verified": True, "active": False},
    )
    db.refresh(user)

    assert response.status_code == 422
    assert user.platform_admin is False
    assert user.email_verified is False
    assert user.active is True
    assert user.email == "fictional@example.test"


def test_profile_fields_are_bounded_and_extra_fields_forbidden(client, make_user, token_for):
    user = make_user()
    headers = bearer(token_for(user))

    too_long = client.patch("/api/v1/me/profile", headers=headers, json={"nickname": "n" * 65})
    blank_tag = client.patch("/api/v1/me/profile", headers=headers, json={"tags": ["   "]})
    extra = client.patch("/api/v1/me/profile", headers=headers, json={"email": "private@example.test"})

    assert too_long.status_code == blank_tag.status_code == extra.status_code == 422

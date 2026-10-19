"""API-boundary coverage for Supabase identity provisioning.

The verifier is replaced with a fixed VerifiedSupabaseIdentity so these tests
exercise provisioning and authorization without contacting Supabase or Google.
JWT/JWKS and Auth-response parsing belong to test_supabase_auth.py.
"""
from dataclasses import FrozenInstanceError, fields
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import Response


class _VerifierStub:
    def __init__(self, identity_type):
        self.identity_type = identity_type
        self.identities = {}

    def allow(self, token, *, user_id, email, email_verified):
        identity = self.identity_type(
            user_id=user_id,
            email=email,
            email_verified=email_verified,
        )
        self.identities[token] = identity
        return identity

    def __call__(self, token, settings):
        from app.core.errors import DomainError

        assert settings.auth_provider == "supabase"
        identity = self.identities.get(token)
        if identity is None:
            raise DomainError(
                "authentication_required",
                "Authentication could not be verified.",
                401,
            )
        return identity


@pytest.fixture
def supabase_verifier(monkeypatch):
    from app.domains.identity import supabase_auth

    stub = _VerifierStub(supabase_auth.VerifiedSupabaseIdentity)
    monkeypatch.setattr(supabase_auth, "verify_supabase_identity", stub)
    return stub


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_new_verified_plm_identity_gets_private_incomplete_profile(
    client, db, supabase_verifier
):
    from app.domains.identity.models import User
    from app.domains.organizations.models import OrgMembership

    user_id = str(uuid4())
    token = "sprint15-mock-plm-session"
    identity = supabase_verifier.allow(
        token,
        user_id=user_id,
        email="student@students.plm.edu.ph",
        email_verified=True,
    )

    assert {field.name for field in fields(identity)} == {
        "user_id",
        "email",
        "email_verified",
    }
    with pytest.raises(FrozenInstanceError):
        identity.email = "attacker@plm.edu.ph"

    response = client.get("/api/v1/me", headers=_bearer(token))

    assert response.status_code == 200
    actor = response.json()
    assert actor["id"] == user_id
    assert actor["eligible"] is True
    assert actor["profile_complete"] is False
    assert actor["platform_admin"] is False
    assert actor["grants"] == []
    assert "email" not in actor

    db.expire_all()
    user = db.get(User, user_id)
    assert user is not None
    assert user.email == "student@students.plm.edu.ph"
    assert user.email_verified is True
    assert user.nickname is None
    assert user.age_bracket is None
    assert user.tags == []
    assert user.pronouns is None
    assert user.icebreaker is None
    assert user.persona_visible is False
    assert db.scalar(
        select(func.count(OrgMembership.id)).where(OrgMembership.user_id == user_id)
    ) == 0

    profile = client.get("/api/v1/me/profile", headers=_bearer(token))
    assert profile.status_code == 200
    assert profile.json() == {
        "nickname": None,
        "age_bracket": None,
        "tags": [],
        "pronouns": None,
        "icebreaker": None,
        "persona_visible": False,
    }


def test_personal_google_identity_can_browse_but_cannot_register(
    client, db, make_event, supabase_verifier
):
    from app.domains.registrations.models import Registration

    event = make_event()
    user_id = str(uuid4())
    token = "sprint15-mock-personal-session"
    supabase_verifier.allow(
        token,
        user_id=user_id,
        email="developer@example.invalid",
        email_verified=True,
    )

    actor = client.get("/api/v1/me", headers=_bearer(token))
    assert actor.status_code == 200
    assert actor.json()["eligible"] is False

    public_event = client.get(
        f"/api/v1/events/{event.id}", headers=_bearer(token)
    )
    assert public_event.status_code == 200
    assert public_event.json()["id"] == event.id

    denied = client.post(
        f"/api/v1/events/{event.id}/registrations",
        headers={**_bearer(token), "Idempotency-Key": "sprint15-personal-01"},
    )
    assert denied.status_code == 403
    assert db.scalar(
        select(func.count(Registration.id)).where(
            Registration.event_id == event.id,
            Registration.user_id == user_id,
        )
    ) == 0


def test_trusted_email_sync_preserves_existing_profile_admin_and_membership(
    client, db, make_user, make_org, supabase_verifier
):
    from app.domains.identity.models import User

    user_id = str(uuid4())
    existing = make_user(
        id=user_id,
        email="old-address@example.invalid",
        email_verified=False,
        platform_admin=True,
        nickname="Existing nickname",
        age_bracket="25-34",
        tags=["arts"],
        pronouns="they/them",
        icebreaker="Existing profile text",
        persona_visible=True,
    )
    organization = make_org(owner=existing)
    token = "sprint15-mock-existing-session"
    supabase_verifier.allow(
        token,
        user_id=user_id,
        email="updated@students.plm.edu.ph",
        email_verified=True,
    )

    response = client.get("/api/v1/me", headers=_bearer(token))

    assert response.status_code == 200
    actor = response.json()
    assert actor["eligible"] is True
    assert actor["profile_complete"] is True
    assert actor["platform_admin"] is True
    assert len(actor["grants"]) == 1
    assert actor["grants"][0]["org_id"] == organization.id
    assert actor["grants"][0]["role"] == "owner"
    assert "updated@students.plm.edu.ph" not in response.text

    db.expire_all()
    user = db.get(User, user_id)
    assert user is not None
    assert user.email == "updated@students.plm.edu.ph"
    assert user.email_verified is True
    assert user.active is True
    assert user.platform_admin is True
    assert user.nickname == "Existing nickname"
    assert user.age_bracket == "25-34"
    assert user.tags == ["arts"]
    assert user.pronouns == "they/them"
    assert user.icebreaker == "Existing profile text"
    assert user.persona_visible is True


def test_email_collision_rejects_without_linking_or_disclosing_account(
    client, db, make_user, supabase_verifier
):
    from app.domains.identity.models import User

    collision_email = "collision@plm.edu.ph"
    existing_id = str(uuid4())
    new_subject = str(uuid4())
    existing = make_user(
        id=existing_id,
        email=collision_email,
        nickname="Original account",
    )
    token = "sprint15-mock-colliding-session"
    supabase_verifier.allow(
        token,
        user_id=new_subject,
        email=collision_email,
        email_verified=True,
    )

    collision = client.get("/api/v1/me", headers=_bearer(token))
    unknown = client.get(
        "/api/v1/me", headers=_bearer("sprint15-unrecognized-provider-token")
    )

    assert collision.status_code == unknown.status_code == 401
    assert collision.json()["error"] == unknown.json()["error"]
    assert collision_email not in collision.text
    db.expire_all()
    persisted = db.get(User, existing_id)
    assert persisted is not None
    assert persisted.email == collision_email
    assert persisted.nickname == "Original account"
    assert db.get(User, new_subject) is None


def test_deactivated_supabase_user_remains_denied(client, db, supabase_verifier):
    from app.domains.identity.models import User

    user_id = str(uuid4())
    token = "sprint15-mock-deactivated-session"
    supabase_verifier.allow(
        token,
        user_id=user_id,
        email="deactivated@students.plm.edu.ph",
        email_verified=True,
    )

    first = client.get("/api/v1/me", headers=_bearer(token))
    assert first.status_code == 200

    user = db.get(User, user_id)
    assert user is not None
    user.active = False
    db.commit()

    denied = client.get("/api/v1/me", headers=_bearer(token))
    assert denied.status_code == 401
    assert denied.json()["error"] == {
        "code": "authentication_required",
        "message": "Authentication could not be verified.",
    }
    db.refresh(user)
    assert user.active is False


def test_supabase_mode_rejects_fixture_tokens_and_hides_fixture_catalog(
    client, db, monkeypatch
):
    from app import local_demo
    from app.core.config import get_settings
    from app.core.errors import DomainError
    from app.domains.identity import supabase_auth
    from app.domains.events.models import Event
    from app.domains.identity.models import User
    from app.domains.organizations.models import OrgMembership, Organization

    monkeypatch.setattr(
        supabase_auth,
        "_jwks_client",
        lambda issuer: pytest.fail("untrusted tokens must fail before any JWKS request"),
    )
    for foreign_token in (
        "sprint15-unrecognized-fixture-token",
        "sprint15-unrecognized-google-provider-token",
    ):
        response = client.get("/api/v1/me", headers=_bearer(foreign_token))
        assert response.status_code == 401
    assert db.scalar(select(func.count(User.id))) == 0

    # Exercise the catalog guard with a loopback request in local real mode;
    # TestClient's default non-loopback peer would otherwise mask this branch.
    real_local_settings = get_settings().model_copy(update={"environment": "local"})
    monkeypatch.setattr(local_demo, "get_settings", lambda: real_local_settings)
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/local-demo/accounts",
            "raw_path": b"/api/v1/local-demo/accounts",
            "query_string": b"",
            "headers": [(b"host", b"127.0.0.1")],
            "client": ("127.0.0.1", 54321),
            "server": ("127.0.0.1", 8011),
        }
    )
    with pytest.raises(DomainError) as error:
        local_demo.accounts(request, Response())

    assert error.value.status == 404
    assert error.value.code == "local_demo_unavailable"
    assert db.scalar(select(func.count(Event.id))) == 0
    assert db.scalar(select(func.count(Organization.id))) == 0
    assert db.scalar(select(func.count(OrgMembership.id))) == 0


def test_api_logs_and_actor_response_omit_raw_token_and_email(
    client, caplog, supabase_verifier
):
    import logging

    user_id = str(uuid4())
    token = "sprint15-private-access-token-sentinel"
    email = "private-user-sentinel@example.invalid"
    supabase_verifier.allow(
        token,
        user_id=user_id,
        email=email,
        email_verified=True,
    )

    with caplog.at_level(logging.INFO, logger="intraspot.actions"):
        response = client.get("/api/v1/me", headers=_bearer(token))

    assert response.status_code == 200
    assert token not in response.text
    assert email not in response.text
    assert token not in caplog.text
    assert email not in caplog.text

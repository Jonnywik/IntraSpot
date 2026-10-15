import base64
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import now


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_current_actor_requires_bearer(client):
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


@pytest.mark.parametrize("case", ["expired", "issuer", "audience", "null_subject", "invalid_subject"])
def test_rejects_invalid_required_claims(client, make_user, token_for, case):
    user = make_user()
    overrides = {
        "expired": {"exp": now() - timedelta(seconds=5)},
        "issuer": {"iss": "urn:other"},
        "audience": {"aud": "other-api"},
        "null_subject": {"sub": None},
        "invalid_subject": {"sub": "not-a-uuid"},
    }[case]

    response = client.get("/api/v1/me", headers=bearer(token_for(user, **overrides)))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_missing_subject_claim_is_rejected(auth_dependency_client, monkeypatch):
    import app.core.auth as auth_module

    monkeypatch.setattr(
        auth_module.jwt,
        "decode",
        lambda *_args, **_kwargs: {"iss": "urn:intraspot:local", "aud": "intraspot-api", "exp": 2_000_000_000},
    )

    response = auth_dependency_client.get("/required", headers=bearer("signed-local-token"))

    assert response.status_code == 401


def test_rejects_forged_signature_and_unknown_algorithm(client, make_user, token_for):
    user = make_user()
    token = token_for(user)
    header, payload, signature = token.split(".")
    changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    forged = ".".join((header, payload, changed_signature))

    assert client.get("/api/v1/me", headers=bearer(forged)).status_code == 401

    header_data = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
    header_data["alg"] = "HS256"
    unknown_algorithm = base64.urlsafe_b64encode(
        json.dumps(header_data, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    unsupported = ".".join((unknown_algorithm, payload, signature))

    assert client.get("/api/v1/me", headers=bearer(unsupported)).status_code == 401


def test_rejects_unknown_and_inactive_users(client, make_user, token_for):
    unknown_id = str(uuid4())
    inactive = make_user(active=False)

    unknown_response = client.get("/api/v1/me", headers=bearer(token_for(unknown_id)))
    inactive_response = client.get("/api/v1/me", headers=bearer(token_for(inactive)))

    assert unknown_response.status_code == inactive_response.status_code == 401
    assert unknown_response.json()["error"] == inactive_response.json()["error"]


@pytest.mark.parametrize(
    ("email", "email_verified", "expected"),
    [
        ("fictional@plm.edu.ph", True, True),
        ("fictional@students.plm.edu.ph", True, True),
        ("fictional@PLM.EDU.PH", True, True),
        ("fictional@plm.edu.ph.attacker.test", True, False),
        ("fictional@notplm.edu.ph", True, False),
        ("fictional@students.plm.edu.ph", False, False),
    ],
)
def test_eligibility_uses_verified_database_email(client, make_user, token_for, email, email_verified, expected):
    user = make_user(email=email, email_verified=email_verified)
    token = token_for(user, email="attacker@plm.edu.ph", email_verified=True, eligible=True)

    response = client.get("/api/v1/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["eligible"] is expected
    assert "email" not in response.json()


def test_platform_admin_and_grants_come_from_database(client, make_user, make_org, token_for):
    user = make_user(platform_admin=False)
    organization = make_org(owner=user)

    response = client.get(
        "/api/v1/me",
        headers=bearer(token_for(user, platform_admin=True, roles=["owner"], grants=[organization.id])),
    )

    assert response.status_code == 200
    actor = response.json()
    assert set(actor) == {"id", "nickname", "eligible", "profile_complete", "platform_admin", "grants", "communication_restricted"}
    assert actor['communication_restricted'] is False
    assert actor["platform_admin"] is False
    assert user.email not in response.text
    assert actor["grants"] == [
        {
            "org_id": organization.id,
            "org_name": organization.name,
            "role": "owner",
            "accreditation_status": organization.accreditation_status,
        }
    ]


def test_only_active_membership_grants_are_returned(client, db, make_user, make_org, token_for):
    from app.domains.organizations.models import OrgMembership

    user = make_user()
    organization = make_org(owner=user)
    membership = db.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == organization.id,
            OrgMembership.user_id == user.id,
        )
    )
    membership.active = False
    db.commit()

    response = client.get("/api/v1/me", headers=bearer(token_for(user)))

    assert response.status_code == 200
    assert response.json()["grants"] == []


def test_actor_refreshes_role_accreditation_and_revocation_with_same_token(client, db, make_user, make_org, token_for):
    from app.domains.organizations.models import OrgMembership

    user = make_user()
    organization = make_org(owner=user)
    membership = db.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == organization.id,
            OrgMembership.user_id == user.id,
        )
    )
    headers = bearer(token_for(user))

    original = client.get("/api/v1/me", headers=headers)
    assert original.status_code == 200
    assert original.json()["grants"][0]["role"] == "owner"
    assert original.json()["grants"][0]["accreditation_status"] == "approved"

    membership.role = "admin"
    organization.accreditation_status = "pending"
    db.commit()

    changed = client.get("/api/v1/me", headers=headers)
    assert changed.status_code == 200
    assert changed.json()["grants"] == [
        {
            "org_id": organization.id,
            "org_name": organization.name,
            "role": "admin",
            "accreditation_status": "pending",
        }
    ]

    membership.active = False
    db.commit()

    revoked = client.get("/api/v1/me", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["grants"] == []


def test_platform_admin_access_requires_eligible_active_database_identity(client, make_user, token_for):
    ineligible_admin = make_user(
        email="fictional@example.test",
        email_verified=True,
        platform_admin=True,
    )
    eligible_non_admin = make_user()
    inactive_admin = make_user(active=False, platform_admin=True)

    ineligible_response = client.get(
        "/api/v1/platform-admin/organizations",
        headers=bearer(token_for(ineligible_admin, eligible=True, platform_admin=False)),
    )
    non_admin_response = client.get(
        "/api/v1/platform-admin/organizations",
        headers=bearer(token_for(eligible_non_admin, platform_admin=True)),
    )
    inactive_response = client.get(
        "/api/v1/platform-admin/organizations",
        headers=bearer(token_for(inactive_admin, eligible=True, platform_admin=True)),
    )

    assert ineligible_response.status_code == 403
    assert ineligible_response.json()["error"]["code"] == "organization_forbidden"
    assert non_admin_response.status_code == 403
    assert non_admin_response.json()["error"]["code"] == "platform_admin_required"
    assert inactive_response.status_code == 401
    assert inactive_response.json()["error"]["code"] == "authentication_required"


def test_optional_actor_allows_guest_but_not_invalid_supplied_token(auth_dependency_client, make_user, token_for):
    user = make_user()
    guest = auth_dependency_client.get("/optional")
    signed_in = auth_dependency_client.get("/optional", headers=bearer(token_for(user)))
    invalid = auth_dependency_client.get("/optional", headers={"Authorization": "Bearer malformed"})
    wrong_scheme = auth_dependency_client.get("/optional", headers={"Authorization": "Basic abc"})

    assert guest.status_code == 200 and guest.json() == {"id": None}
    assert signed_in.status_code == 200 and signed_in.json() == {"id": user.id}
    assert invalid.status_code == wrong_scheme.status_code == 401


def test_require_eligible_returns_actor_or_domain_403(auth_dependency_client, make_user, token_for):
    eligible = make_user()
    ineligible = make_user(email="fictional@example.test", email_verified=True)

    accepted = auth_dependency_client.get("/eligible", headers=bearer(token_for(eligible)))
    denied = auth_dependency_client.get("/eligible", headers=bearer(token_for(ineligible)))

    assert accepted.status_code == 200 and accepted.json() == {"id": eligible.id}
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "plm_email_required"
    assert "example.test" not in denied.text

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.contracts import Actor
from app.db.session import get_db, session_factory
from app.domains.organizations.models import AccreditationDecision, Organization
from app.domains.organizations.service import decide_accreditation


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("field", "value", "expected_status"),
    [("platform_admin", False, 403), ("email_verified", False, 403), ("active", False, 401)],
)
def test_accreditation_endpoint_rechecks_current_admin_identity_for_existing_token(
    client, db, make_user, make_org, token_for, field, value, expected_status,
):
    admin = make_user(platform_admin=True)
    token = token_for(admin)
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="pending")

    setattr(admin, field, value)
    db.commit()

    response = client.post(
        f"/api/v1/platform-admin/organizations/{organization.id}/accreditation-decision",
        headers=auth(token),
        json={"outcome": "approved"},
    )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"]
    db.refresh(organization)
    assert organization.accreditation_status == "pending"
    assert db.scalar(
        select(func.count(AccreditationDecision.id)).where(
            AccreditationDecision.org_id == organization.id,
        )
    ) == 0


def test_failed_accreditation_commit_rolls_back_status_and_audit(
    db, make_user, make_org, monkeypatch,
):
    admin = make_user(platform_admin=True)
    owner = make_user()
    organization = make_org(owner=owner, accreditation_status="pending")
    actor = Actor(
        user_id=admin.id,
        nickname=admin.nickname,
        eligible=True,
        profile_complete=True,
        platform_admin=True,
    )

    transaction = get_db()
    transaction_db = next(transaction)
    try:
        decided = decide_accreditation(transaction_db, actor, organization.id, "approved")
        assert decided.accreditation_status == "approved"
        assert transaction_db.scalar(
            select(func.count(AccreditationDecision.id)).where(
                AccreditationDecision.org_id == organization.id,
            )
        ) == 1

        original_commit = Session.commit

        def fail_commit(session):
            if session.info.get("fail_accreditation_commit"):
                raise RuntimeError("simulated accreditation commit failure")
            return original_commit(session)

        monkeypatch.setattr(Session, "commit", fail_commit)
        transaction_db.info["fail_accreditation_commit"] = True
        with pytest.raises(RuntimeError, match="simulated accreditation commit failure"):
            next(transaction)
    finally:
        transaction.close()

    with session_factory()() as verification_db:
        stored_organization = verification_db.get(Organization, organization.id)
        stored_decisions = list(
            verification_db.scalars(
                select(AccreditationDecision).where(
                    AccreditationDecision.org_id == organization.id,
                )
            )
        )

    assert stored_organization.accreditation_status == "pending"
    assert stored_decisions == []

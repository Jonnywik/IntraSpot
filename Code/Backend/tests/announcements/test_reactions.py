from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.contracts import Actor
from app.db.models import now, uid
from app.db.session import engine
from app.domains.announcements import service
from app.domains.announcements.models import AnnouncementReaction
from app.domains.announcements.schemas import AnnouncementCreate
from app.domains.organizations.models import OrgMembership


def auth(user, token_for):
    return {"Authorization": f"Bearer {token_for(user)}"}


def actor_for(user):
    return Actor(
        user_id=user.id,
        nickname=user.nickname,
        eligible=True,
        profile_complete=True,
        platform_admin=user.platform_admin,
    )


def add_membership(db, organization, user, *, active=True):
    db.add(
        OrgMembership(
            id=uid(), org_id=organization.id, user_id=user.id, role="member", active=active
        )
    )
    db.commit()


def publish(db, organization, owner, *, audience="public", title="Reaction target"):
    created = service.create_announcement(
        db,
        organization.id,
        actor_for(owner),
        AnnouncementCreate(
            title=title,
            body="A fictional announcement for reaction tests.",
            audience=audience,
            client_key=uuid4(),
        ),
    )
    db.commit()
    return created


def test_public_reactions_are_desired_state_and_pending_person_review_does_not_block_them(
    client, db, make_user, make_org, make_event, token_for
):
    from datetime import timedelta

    from app.domains.moderation.models import ContentReport

    owner = make_user()
    reactor = make_user()
    reporter = make_user()
    organization = make_org(owner=owner)
    announcement = publish(db, organization, owner)
    event = make_event(org=organization)
    db.add(
        ContentReport(
            id=uid(),
            event_id=event.id,
            org_id=organization.id,
            reporter_id=reporter.id,
            subject_user_id=reactor.id,
            kind="person",
            target_id=reactor.id,
            reason="other",
            status="open",
            stage="platform",
            deadline=now() + timedelta(days=2),
        )
    )
    db.commit()

    reaction_url = f"/api/v1/announcements/{announcement.id}/reactions"
    anonymous = client.get(reaction_url)
    assert anonymous.status_code == 200
    assert anonymous.json() == {
        "counts": {
            "interested": 0,
            "excited": 0,
            "support": 0,
            "kudos": 0,
            "wow": 0,
            "relate": 0,
        },
        "total": 0,
        "mine": None,
        "can_react": False,
    }

    headers = auth(reactor, token_for)
    first = client.post(reaction_url, json={"reaction": "interested"}, headers=headers)
    retry = client.post(reaction_url, json={"reaction": "interested"}, headers=headers)
    changed = client.post(reaction_url, json={"reaction": "kudos"}, headers=headers)
    cleared = client.post(reaction_url, json={"reaction": None}, headers=headers)
    assert first.status_code == retry.status_code == changed.status_code == cleared.status_code == 200
    assert first.json()["total"] == retry.json()["total"] == 1
    assert first.json()["mine"] == "interested"
    assert retry.json()["counts"]["interested"] == 1
    assert changed.json()["counts"]["interested"] == 0
    assert changed.json()["counts"]["kudos"] == 1
    assert cleared.json()["total"] == 0 and cleared.json()["mine"] is None
    assert set(cleared.json()) == {"counts", "total", "mine", "can_react"}
    assert db.scalar(
        select(func.count(AnnouncementReaction.id)).where(
            AnnouncementReaction.announcement_id == announcement.id
        )
    ) == 0


def test_members_only_details_counts_and_reactions_require_current_eligible_membership(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    member = make_user()
    outsider = make_user()
    admin_elsewhere = make_user(platform_admin=True)
    make_org(owner=admin_elsewhere)
    add_membership(db, organization, member)
    private = publish(db, organization, owner, audience="members")

    detail_url = f"/api/v1/announcements/{private.id}"
    reaction_url = f"{detail_url}/reactions"
    assert client.get(detail_url).status_code == 404
    assert client.get(reaction_url).status_code == 404
    assert client.get(detail_url, headers=auth(outsider, token_for)).status_code == 404
    assert client.get(reaction_url, headers=auth(outsider, token_for)).status_code == 404
    assert client.post(
        reaction_url,
        json={"reaction": "support"},
        headers=auth(outsider, token_for),
    ).status_code == 404
    assert client.get(detail_url, headers=auth(admin_elsewhere, token_for)).status_code == 404

    member_headers = auth(member, token_for)
    assert client.get(detail_url, headers=member_headers).status_code == 200
    accepted = client.post(
        reaction_url, json={"reaction": "support"}, headers=member_headers
    )
    assert accepted.status_code == 200
    assert accepted.json()["mine"] == "support"

    membership = db.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == organization.id, OrgMembership.user_id == member.id
        )
    )
    membership.active = False
    db.commit()
    assert client.get(detail_url, headers=member_headers).status_code == 404
    assert client.get(reaction_url, headers=member_headers).status_code == 404
    assert client.post(
        reaction_url, json={"reaction": "wow"}, headers=member_headers
    ).status_code == 404


def test_concurrent_retries_for_same_announcement_reaction_create_one_row(
    db, make_user, make_org
):
    owner = make_user()
    reactor = make_user()
    organization = make_org(owner=owner)
    announcement = publish(db, organization, owner)
    actor = actor_for(reactor)
    workers = 3
    barrier = Barrier(workers)

    def set_same_reaction(_index):
        barrier.wait(timeout=10)
        with Session(engine(), expire_on_commit=False) as session:
            summary = service.set_reaction(session, announcement.id, actor, "excited")
            session.commit()
            return summary

    with ThreadPoolExecutor(max_workers=workers) as executor:
        summaries = list(executor.map(set_same_reaction, range(workers)))

    assert all(summary.total == 1 and summary.mine == "excited" for summary in summaries)
    assert db.scalar(
        select(func.count(AnnouncementReaction.id)).where(
            AnnouncementReaction.announcement_id == announcement.id,
            AnnouncementReaction.user_id == reactor.id,
        )
    ) == 1
    assert db.scalar(
        select(AnnouncementReaction.kind).where(
            AnnouncementReaction.announcement_id == announcement.id
        )
    ) == "excited"


"""Real PostgreSQL checks for Sprint 22 event visibility boundaries."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.communication_schemas import ContentCreate
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.eventsafety.models import EventControl, OrganizationSuspension
from app.domains.featured import service as featured_service
from app.domains.featured.models import FeaturedRequest
from app.domains.featured.schemas import FeaturedDecisionInput
from app.domains.identity.service import actor_for_user
from app.domains.media import service as media_service
from app.domains.media.models import MediaAsset
from app.domains.planning import service as planning_service
from app.domains.planning.models import SavedEvent
from app.domains.registrations.models import Registration
from app.domains.social import service as social_service
from app.domains.social.models import EventComment, EventReaction


_VISIBILITY_RESTRICTIONS = ("org_hidden", "platform_hidden", "suspension")


def _set_restriction(db, event, restriction):
    if restriction == "suspension":
        db.add(OrganizationSuspension(
            org_id=event.org_id,
            suspended_until=now() + timedelta(days=1),
            version=1,
        ))
    else:
        db.add(EventControl(
            event_id=event.id,
            org_hidden=restriction == "org_hidden",
            platform_hidden=restriction == "platform_hidden",
            removed=False,
            cancelled=False,
            version=0,
            org_reviewed_at=None,
        ))
    db.commit()


def _set_terminal(db, event, terminal_state):
    db.add(EventControl(
        event_id=event.id,
        org_hidden=False,
        platform_hidden=False,
        removed=terminal_state == "removed",
        cancelled=terminal_state == "cancelled",
        version=0,
        org_reviewed_at=None,
    ))
    db.commit()


def _register(db, event, user, status="confirmed"):
    registration = Registration(
        id=uid(),
        user_id=user.id,
        event_id=event.id,
        status=status,
        admission_order=1,
        confirmed_at=now() if status == "confirmed" else None,
    )
    db.add(registration)
    db.commit()
    return registration


def _owned_event(make_event, make_org, make_user):
    owner = make_user()
    organization = make_org(owner=owner)
    return owner, organization, make_event(org=organization)


def _attach_banner(db, event, owner):
    asset = MediaAsset(
        id=uid(),
        org_id=event.org_id,
        kind="banner",
        width=2,
        height=2,
        byte_size=16,
        created_by=owner.id,
    )
    db.add(asset)
    db.flush()
    event.banner_media_id = asset.id
    db.commit()
    return asset


def _create_featured_request(db, event, owner):
    return featured_service.create_request(db, actor_for_user(db, owner), event.id)


def _approve_featured(db, event, owner, platform_admin, starts_at):
    request = _create_featured_request(db, event, owner)
    featured_service.decide_request(
        db,
        actor_for_user(db, platform_admin),
        request.id,
        FeaturedDecisionInput(
            action="approve",
            version=request.version,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
        ),
    )
    return request


@pytest.mark.parametrize("restriction", _VISIBILITY_RESTRICTIONS)
def test_saved_projection_is_redacted_while_the_private_bookmark_remains(
    db, make_event, make_user, restriction
):
    user = make_user()
    event = make_event(title="Restricted saved event title")
    saved = planning_service.save_event(db, user.id, event.id)
    assert saved.saved is True

    _set_restriction(db, event, restriction)
    projected = planning_service.list_saved_events(db, user.id)

    assert len(projected) == 1
    assert projected[0].event_id == event.id
    assert projected[0].event is None
    assert planning_service.saved_event_state(db, user.id, event.id).saved is True
    assert db.get(SavedEvent, (user.id, event.id)) is not None


def test_conflicts_exclude_hidden_and_suspended_public_events(
    db, make_event, make_org, make_user
):
    user = make_user()
    start = now() + timedelta(days=10)
    target = make_event(starts_at=start, ends_at=start + timedelta(hours=2))
    hidden = make_event(
        starts_at=start + timedelta(minutes=20),
        ends_at=start + timedelta(hours=1),
    )
    suspended_owner = make_user()
    suspended_org = make_org(owner=suspended_owner)
    suspended = make_event(
        org=suspended_org,
        starts_at=start + timedelta(minutes=40),
        ends_at=start + timedelta(hours=1, minutes=20),
    )
    visible = make_event(
        starts_at=start + timedelta(hours=1, minutes=20),
        ends_at=start + timedelta(hours=1, minutes=40),
    )
    for event in (hidden, suspended, visible):
        _register(db, event, user)

    _set_restriction(db, hidden, "org_hidden")
    _set_restriction(db, suspended, "suspension")

    conflicts = planning_service.event_conflicts(db, user.id, target.id)

    assert [item.event_id for item in conflicts.conflicts] == [visible.id]


@pytest.mark.parametrize("restriction", _VISIBILITY_RESTRICTIONS)
def test_banner_public_reads_follow_policy_and_private_draft_manager_access_remains(
    db, make_event, make_org, make_user, monkeypatch, restriction
):
    owner, organization, event = _owned_event(make_event, make_org, make_user)
    public_asset = _attach_banner(db, event, owner)
    monkeypatch.setattr(media_service, "read_webp", lambda _media_id, *, db=None: b"test-webp")
    _set_restriction(db, event, restriction)

    with pytest.raises(DomainError) as hidden:
        media_service.authorize_and_read(db, None, public_asset.id)
    assert hidden.value.status == 404
    assert media_service.authorize_and_read(
        db, actor_for_user(db, owner), public_asset.id
    ) == b"test-webp"

    draft = make_event(org=organization, status="draft", published_at=None)
    private_asset = _attach_banner(db, draft, owner)
    assert media_service.authorize_and_read(
        db, actor_for_user(db, owner), private_asset.id
    ) == b"test-webp"


@pytest.mark.parametrize("restriction", _VISIBILITY_RESTRICTIONS)
def test_social_reads_and_mutations_allow_participants_and_staff_only(
    db, make_event, make_org, make_user, restriction
):
    owner, _organization, event = _owned_event(make_event, make_org, make_user)
    participant = make_user()
    outsider = make_user()
    _register(db, event, participant)
    _set_restriction(db, event, restriction)

    participant_actor = actor_for_user(db, participant)
    owner_actor = actor_for_user(db, owner)
    outsider_actor = actor_for_user(db, outsider)

    assert social_service.list_comments(db, event.id, participant_actor).items == []
    assert social_service.list_comments(db, event.id, owner_actor).items == []
    for operation in (
        lambda: social_service.list_comments(db, event.id, outsider_actor),
        lambda: social_service.get_reaction_summary(db, event.id, outsider_actor),
        lambda: social_service.create_comment(
            db,
            event.id,
            outsider.id,
            ContentCreate(body="Outsider comment", client_key=uuid4()),
        ),
        lambda: social_service.set_reaction(db, event.id, outsider.id, "interested"),
    ):
        with pytest.raises(DomainError) as denied:
            operation()
        assert denied.value.status == 404

    comment = social_service.create_comment(
        db,
        event.id,
        participant.id,
        ContentCreate(body="Participant comment", client_key=uuid4()),
    )
    participant_reaction = social_service.set_reaction(
        db, event.id, participant.id, "interested"
    )
    staff_reaction = social_service.set_reaction(db, event.id, owner.id, "support")

    assert comment.body == "Participant comment"
    assert participant_reaction.total == 1
    assert staff_reaction.total == 2
    assert social_service.list_comments(db, event.id, owner_actor).items[0].body == comment.body


@pytest.mark.parametrize("terminal_state", ("removed", "cancelled"))
def test_terminal_events_reject_social_writes_without_deleting_existing_content(
    db, make_event, make_org, make_user, terminal_state
):
    _owner, _organization, event = _owned_event(make_event, make_org, make_user)
    participant = make_user()
    _register(db, event, participant)
    existing = social_service.create_comment(
        db,
        event.id,
        participant.id,
        ContentCreate(body="Before terminal state", client_key=uuid4()),
    )
    _set_terminal(db, event, terminal_state)

    operations = (
        lambda: social_service.create_comment(
            db,
            event.id,
            participant.id,
            ContentCreate(body="After terminal state", client_key=uuid4()),
        ),
        lambda: social_service.set_reaction(db, event.id, participant.id, "interested"),
        lambda: social_service.delete_comment(db, event.id, existing.id, participant.id),
    )
    for operation in operations:
        with pytest.raises(DomainError) as denied:
            operation()
        assert denied.value.status == 409

    assert db.scalar(select(func.count(EventComment.id)).where(EventComment.event_id == event.id)) == 1
    assert db.scalar(select(func.count(EventReaction.id)).where(EventReaction.event_id == event.id)) == 0


def test_featured_badges_exclude_hidden_and_suspended_events(
    db, make_event, make_org, make_user
):
    platform_admin = make_user(platform_admin=True)
    boundary = now()
    specs = (
        ("org_hidden", boundary + timedelta(minutes=10)),
        ("suspension", boundary + timedelta(minutes=70)),
        (None, boundary + timedelta(minutes=130)),
    )
    events = []
    for restriction, starts_at in specs:
        owner, _organization, event = _owned_event(make_event, make_org, make_user)
        _approve_featured(db, event, owner, platform_admin, starts_at)
        if restriction is not None:
            _set_restriction(db, event, restriction)
        events.append((event, restriction, starts_at))

    _, _, hidden_start = events[0]
    _, _, suspended_start = events[1]
    visible_event, _, visible_start = events[2]

    assert featured_service.active_featured_event_ids(
        db, [event for event, _, _ in events], at=hidden_start + timedelta(minutes=1)
    ) == set()
    assert featured_service.active_featured_event_ids(
        db, [event for event, _, _ in events], at=suspended_start + timedelta(minutes=1)
    ) == set()
    assert featured_service.active_featured_event_ids(
        db, [event for event, _, _ in events], at=visible_start + timedelta(minutes=1)
    ) == {visible_event.id}


def test_featured_requests_and_decisions_reject_terminal_events_by_policy(
    db, make_event, make_org, make_user
):
    owner, _organization, decision_event = _owned_event(make_event, make_org, make_user)
    platform_admin = make_user(platform_admin=True)
    pending = _create_featured_request(db, decision_event, owner)
    _set_terminal(db, decision_event, "removed")

    with pytest.raises(DomainError) as denied_decision:
        featured_service.decide_request(
            db,
            actor_for_user(db, platform_admin),
            pending.id,
            FeaturedDecisionInput(action="reject", version=pending.version),
        )
    assert denied_decision.value.status == 409
    assert db.scalar(
        select(func.count(FeaturedRequest.id)).where(
            FeaturedRequest.event_id == decision_event.id
        )
    ) == 1

    request_owner, _, request_event = _owned_event(
        make_event, make_org, make_user
    )
    _set_terminal(db, request_event, "cancelled")
    with pytest.raises(DomainError) as denied_request:
        _create_featured_request(db, request_event, request_owner)
    assert denied_request.value.status == 409
    assert db.scalar(
        select(func.count(FeaturedRequest.id)).where(
            FeaturedRequest.event_id == request_event.id
        )
    ) == 0

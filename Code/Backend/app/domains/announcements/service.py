"""Organization-scoped announcement access, authoring, and reactions."""

from datetime import datetime
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.communication import require_communication_allowed
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.memberships import policy as membership_policy
from app.domains.organizations import service as organization_service
from app.domains.organizations.models import Organization, OrgMembership
from app.domains.social.schemas import REACTION_KINDS, ReactionKind, ReactionSummary

from .models import Announcement, AnnouncementReaction, AnnouncementRevision
from .schemas import (
    AnnouncementAudience,
    AnnouncementCreate,
    AnnouncementOut,
    AnnouncementPatch,
    AnnouncementRevisionAction,
    AnnouncementRevisionOut,
    AnnouncementState,
)

_MANAGER_ROLES = ("owner", "admin")
_REVISION_ACTIONS = {"publish", "edit", "remove", "hide", "restore"}


def _not_found() -> DomainError:
    return DomainError("announcement_not_found", "Announcement was not found.", 404)


def _conflict(message: str = "This announcement changed in another window. Reload before continuing.") -> DomainError:
    return DomainError("announcement_conflict", message, 409)


def _approved_organization(db: Session, org_id: str) -> Organization:
    organization = db.scalar(
        select(Organization)
        .where(Organization.id == str(org_id))
        .execution_options(populate_existing=True)
    )
    if organization is None or organization.accreditation_status != "approved":
        raise _not_found()
    return organization


def _active_membership(db: Session, org_id: str, user_id: str) -> OrgMembership | None:
    return db.scalar(
        select(OrgMembership)
        .where(
            OrgMembership.org_id == str(org_id),
            OrgMembership.user_id == str(user_id),
            OrgMembership.active.is_(True),
        )
        .execution_options(populate_existing=True)
    )


def _current_member(db: Session, org_id: str, actor: Actor | None) -> bool:
    if actor is None or not membership_policy.eligible_user(db, actor.user_id):
        return False
    return _active_membership(db, org_id, actor.user_id) is not None


def _project(
    post: Announcement,
    organization_name: str,
) -> AnnouncementOut:
    state: AnnouncementState = (
        "removed" if post.removed_at is not None
        else "hidden" if post.hidden_at is not None
        else "visible"
    )
    return AnnouncementOut(
        id=post.id,
        org_id=post.org_id,
        organization_name=organization_name,
        title=post.title,
        body=post.body,
        audience=post.audience,
        version=post.version,
        created_at=post.created_at,
        updated_at=post.updated_at,
        edited_at=post.edited_at,
        state=state,
    )


def _get_manager_organization(
    db: Session,
    actor: Actor,
    org_id: str,
    *,
    lock: bool,
) -> Organization:
    organization, _membership = organization_service.require_manager_membership(
        db, actor, str(org_id), lock=lock
    )
    if (
        not membership_policy.eligible_user(db, actor.user_id)
        or organization.accreditation_status != "approved"
    ):
        raise DomainError(
            "organization_forbidden",
            "Approved, eligible organization manager access is required.",
            403,
        )
    return organization


def _manager_announcement(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor,
    *,
    lock: bool,
) -> tuple[Organization, Announcement]:
    post_id = str(announcement_id)
    org_id = db.scalar(select(Announcement.org_id).where(Announcement.id == post_id))
    if org_id is None:
        raise _not_found()

    organization_query = select(Organization).where(Organization.id == org_id)
    if lock:
        organization_query = organization_query.with_for_update().execution_options(
            populate_existing=True
        )
    else:
        organization_query = organization_query.execution_options(populate_existing=True)
    organization = db.scalar(organization_query)
    if organization is None or organization.accreditation_status != "approved":
        raise _not_found()

    post_query = select(Announcement).where(
        Announcement.id == post_id,
        Announcement.org_id == organization.id,
    )
    if lock:
        post_query = post_query.with_for_update().execution_options(populate_existing=True)
    else:
        post_query = post_query.execution_options(populate_existing=True)
    post = db.scalar(post_query)
    if post is None:
        raise _not_found()

    membership = _active_membership(db, organization.id, actor.user_id)
    if (
        not membership_policy.eligible_user(db, actor.user_id)
        or membership is None
        or membership.role not in _MANAGER_ROLES
    ):
        raise _not_found()
    return organization, post


def get_readable_announcement(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor | None,
    lock: bool = False,
) -> Announcement:
    """Return visible content only when the current database policy permits reading it."""
    post_id = str(announcement_id)
    if lock:
        org_id = db.scalar(select(Announcement.org_id).where(Announcement.id == post_id))
        if org_id is None:
            raise _not_found()

        organization = db.scalar(
            select(Organization)
            .where(Organization.id == org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        post = db.scalar(
            select(Announcement)
            .where(Announcement.id == post_id, Announcement.org_id == org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        post = db.scalar(
            select(Announcement)
            .where(Announcement.id == post_id)
            .execution_options(populate_existing=True)
        )
        organization = (
            db.scalar(
                select(Organization)
                .where(Organization.id == post.org_id)
                .execution_options(populate_existing=True)
            )
            if post is not None
            else None
        )

    if (
        post is None
        or organization is None
        or organization.accreditation_status != "approved"
        or post.hidden_at is not None
        or post.removed_at is not None
    ):
        raise _not_found()
    if post.audience == "members" and not _current_member(db, post.org_id, actor):
        raise _not_found()
    return post


def list_announcements(
    db: Session,
    org_id: str | UUID,
    actor: Actor | None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[AnnouncementOut]:
    if not 1 <= limit <= 100 or offset < 0:
        raise DomainError("invalid_pagination", "Use a limit from 1 to 100 and a nonnegative offset.", 422)
    organization = _approved_organization(db, str(org_id))
    can_read_members = _current_member(db, organization.id, actor)

    statement = select(Announcement).where(
        Announcement.org_id == organization.id,
        Announcement.hidden_at.is_(None),
        Announcement.removed_at.is_(None),
    )
    if not can_read_members:
        statement = statement.where(Announcement.audience == "public")
    posts = db.scalars(
        statement.order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_project(post, organization.name) for post in posts]


def list_managed_announcements(
    db: Session,
    org_id: str | UUID,
    actor: Actor,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[AnnouncementOut]:
    if not 1 <= limit <= 100 or offset < 0:
        raise DomainError("invalid_pagination", "Use a limit from 1 to 100 and a nonnegative offset.", 422)
    organization = _get_manager_organization(db, actor, str(org_id), lock=False)
    posts = db.scalars(
        select(Announcement)
        .where(Announcement.org_id == organization.id)
        .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_project(post, organization.name) for post in posts]


def get_announcement(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor | None,
) -> AnnouncementOut:
    post = get_readable_announcement(db, announcement_id, actor)
    organization = _approved_organization(db, post.org_id)
    return _project(post, organization.name)


def create_announcement(
    db: Session,
    org_id: str | UUID,
    actor: Actor,
    payload: AnnouncementCreate,
    at: datetime | None = None,
) -> AnnouncementOut:
    organization = _get_manager_organization(db, actor, str(org_id), lock=True)
    timestamp = at or now()
    key = str(payload.client_key)
    create_hash = sha256(
        json.dumps(
            [payload.title, payload.body, payload.audience],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    existing = db.scalar(
        select(Announcement)
        .where(
            Announcement.org_id == organization.id,
            Announcement.created_by == actor.user_id,
            Announcement.client_key == key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.create_hash != create_hash:
            raise DomainError(
                "idempotency_conflict",
                "This client key was already used for different announcement content.",
                409,
            )
        return _project(existing, organization.name)

    require_communication_allowed(db, actor.user_id, at=timestamp, lock=True)

    post = Announcement(
        id=uid(),
        org_id=organization.id,
        created_by=actor.user_id,
        title=payload.title,
        body=payload.body,
        audience=payload.audience,
        version=1,
        client_key=key,
        create_hash=create_hash,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(post)
    db.flush()
    record_revision(db, post, actor.user_id, "publish", timestamp)
    db.flush()
    return _project(post, organization.name)


def update_announcement(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor,
    payload: AnnouncementPatch,
    if_match: str | None,
    at: datetime | None = None,
) -> AnnouncementOut:
    organization, post = _manager_announcement(
        db, announcement_id, actor, lock=True
    )
    _require_version(post, if_match)
    if post.removed_at is not None:
        raise _conflict("Removed announcements cannot be edited.")
    if post.hidden_at is not None:
        raise _conflict("Platform-hidden announcements cannot be edited.")

    changes = {
        field: getattr(payload, field)
        for field in ("title", "body", "audience")
        if field in payload.model_fields_set
    }
    if not any(getattr(post, field) != value for field, value in changes.items()):
        return _project(post, organization.name)

    timestamp = at or now()
    require_communication_allowed(db, actor.user_id, at=timestamp, lock=True)
    for field, value in changes.items():
        setattr(post, field, value)
    post.version += 1
    post.updated_at = timestamp
    post.edited_at = timestamp
    record_revision(db, post, actor.user_id, "edit", timestamp)
    db.flush()
    return _project(post, organization.name)


def remove_announcement(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor,
    if_match: str | None,
    at: datetime | None = None,
) -> AnnouncementOut:
    organization, post = _manager_announcement(
        db, announcement_id, actor, lock=True
    )
    if post.removed_at is not None:
        return _project(post, organization.name)
    _require_version(post, if_match)

    timestamp = at or now()
    post.version += 1
    post.body = None
    post.removed_at = timestamp
    post.updated_at = timestamp
    record_revision(db, post, actor.user_id, "remove", timestamp)
    db.flush()
    return _project(post, organization.name)


def _require_version(post: Announcement, if_match: str | None) -> None:
    if if_match != f'"{post.version}"':
        raise _conflict("A current quoted If-Match version is required. Reload this announcement and try again.")


def record_revision(
    db: Session,
    post: Announcement,
    actor_id: str,
    action: AnnouncementRevisionAction,
    timestamp: datetime,
) -> AnnouncementRevision:
    """Record the post's current version and state after its caller increments version."""
    if action not in _REVISION_ACTIONS:
        raise ValueError(f"Unsupported announcement revision action: {action}")
    revision = AnnouncementRevision(
        id=uid(),
        announcement_id=post.id,
        version=post.version,
        actor_id=str(actor_id),
        action=action,
        title=post.title,
        body=post.body,
        audience=post.audience,
        created_at=timestamp,
    )
    db.add(revision)
    return revision


def list_announcement_history(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor,
) -> list[AnnouncementRevisionOut]:
    _organization, post = _manager_announcement(
        db, announcement_id, actor, lock=False
    )
    revisions = db.scalars(
        select(AnnouncementRevision)
        .where(AnnouncementRevision.announcement_id == post.id)
        .order_by(AnnouncementRevision.version, AnnouncementRevision.id)
    ).all()
    return [AnnouncementRevisionOut.model_validate(row) for row in revisions]


def _reaction_summary(
    db: Session,
    post: Announcement,
    viewer_id: str | None,
    can_react: bool,
) -> ReactionSummary:
    rows = db.execute(
        select(AnnouncementReaction.kind, func.count(AnnouncementReaction.id))
        .where(AnnouncementReaction.announcement_id == post.id)
        .group_by(AnnouncementReaction.kind)
    ).all()
    counts: dict[ReactionKind, int] = {kind: 0 for kind in REACTION_KINDS}
    for kind, count in rows:
        counts[kind] = count
    mine = (
        db.scalar(
            select(AnnouncementReaction.kind).where(
                AnnouncementReaction.announcement_id == post.id,
                AnnouncementReaction.user_id == viewer_id,
            )
        )
        if viewer_id is not None
        else None
    )
    return ReactionSummary(
        counts=counts,
        total=sum(counts.values()),
        mine=mine,
        can_react=can_react,
    )


def get_reaction_summary(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor | None,
) -> ReactionSummary:
    post = get_readable_announcement(db, announcement_id, actor)
    viewer_id = actor.user_id if actor is not None else None
    can_react = bool(
        viewer_id is not None and membership_policy.eligible_user(db, viewer_id)
    )
    return _reaction_summary(db, post, viewer_id, can_react)


def set_reaction(
    db: Session,
    announcement_id: str | UUID,
    actor: Actor,
    desired: ReactionKind | None,
    at: datetime | None = None,
) -> ReactionSummary:
    post = get_readable_announcement(db, announcement_id, actor, lock=True)
    if not membership_policy.eligible_user(db, actor.user_id):
        raise DomainError(
            "plm_email_required", "A verified PLM email address is required.", 403
        )
    if desired is not None and desired not in REACTION_KINDS:
        raise DomainError("invalid_reaction", "Choose one of the available reactions.", 422)

    timestamp = at or now()
    reaction = db.scalar(
        select(AnnouncementReaction)
        .where(
            AnnouncementReaction.announcement_id == post.id,
            AnnouncementReaction.user_id == str(actor.user_id),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    previous = reaction.kind if reaction is not None else None
    if previous != desired:
        if reaction is None and desired is not None:
            db.add(
                AnnouncementReaction(
                    id=uid(),
                    announcement_id=post.id,
                    user_id=str(actor.user_id),
                    kind=desired,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        elif reaction is not None and desired is None:
            db.delete(reaction)
        elif reaction is not None:
            reaction.kind = desired
            reaction.updated_at = timestamp
    db.flush()
    return _reaction_summary(db, post, str(actor.user_id), can_react=True)


__all__ = [
    "create_announcement",
    "get_announcement",
    "get_readable_announcement",
    "get_reaction_summary",
    "list_announcement_history",
    "list_announcements",
    "list_managed_announcements",
    "record_revision",
    "remove_announcement",
    "set_reaction",
    "update_announcement",
]

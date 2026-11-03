"""Operator-mediated, replay-safe account erasure."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select, text, union
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now
from app.db.session import session_factory
from app.domains.announcements.models import Announcement, AnnouncementReaction
from app.domains.chat.models import ChatMessage
from app.domains.events.models import Event
from app.domains.identity.discovery_models import UserDiscoveryPreferences
from app.domains.identity.models import User
from app.domains.identity.preferences_models import UserPreferences
from app.domains.memberships.models import MembershipApplication, MembershipInvitation
from app.domains.moderation.models import ContentHide, ContentReport
from app.domains.organizations.models import Organization, OrgMembership
from app.domains.ownership.models import OwnershipTransfer, OwnershipTransferAudit
from app.domains.personas.models import EventPersonaVisibility, UserBlock
from app.domains.planning.models import SavedEvent
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.domains.registrations.service import (
    ACTIVE_STATUSES,
    DRAIN_BATCH_SIZE,
    SEAT_STATUSES,
    _clear_reconfirmation,
    _clear_review,
    _drain_event_locked,
    _promote_open_seats_locked,
    catch_up_locked,
)
from app.domains.social.models import EventComment, EventReaction
from app.erasure_models import ErasedAccount, ErasureRequest
from app.notifications import Notification


ERASURE_DELAY = timedelta(days=30)
RECEIPT_RETENTION = timedelta(days=365)
_OWNER_BLOCKER = "owner_transfer_required"
_ADMIN_BLOCKER = "platform_admin_replacement_required"
_PROVIDER_CODES = {
    "provider_revocation_pending",
    "provider_action_required",
    "provider_secret_unavailable",
    "provider_revocation_failed",
    "provider_revocation_complete",
}
_MAX_SCOPE_RETRIES = 4
_RESTORE_DATABASE = re.compile(r"^intraspot_restore_[a-z0-9_]+$")
_ERASED_BODY_HASH = hashlib.sha256(b"intraspot-erased-content").hexdigest()


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _RetryErasureScope(Exception):
    pass


class _ProviderFailure(Exception):
    pass


def _set_fulfillment_timeouts(db: Session) -> None:
    db.execute(text("SET LOCAL lock_timeout = '5s'"))
    db.execute(text("SET LOCAL statement_timeout = '30s'"))


def _uuid(value: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise DomainError("erasure_request_not_found", "The erasure request was not found.", 404) from None
    return str(parsed)


def _account_scope_ids(db: Session, user_id: str) -> tuple[set[str], set[str]]:
    org_ids: set[str] = set()
    event_ids: set[str] = set()

    org_queries = (
        select(OrgMembership.org_id).where(OrgMembership.user_id == user_id),
        select(MembershipApplication.org_id).where(MembershipApplication.user_id == user_id),
        select(MembershipInvitation.org_id).where(
            or_(MembershipInvitation.sender_id == user_id, MembershipInvitation.recipient_id == user_id)
        ),
        select(OwnershipTransfer.org_id).where(
            or_(OwnershipTransfer.from_user_id == user_id, OwnershipTransfer.nominee_id == user_id)
        ),
        select(Announcement.org_id)
        .join(AnnouncementReaction, AnnouncementReaction.announcement_id == Announcement.id)
        .where(AnnouncementReaction.user_id == user_id),
        select(Notification.org_id).where(Notification.user_id == user_id, Notification.org_id.is_not(None)),
    )
    for query in org_queries:
        org_ids.update(db.scalars(query).all())

    event_queries = (
        select(Registration.event_id).where(Registration.user_id == user_id),
        select(RegistrationReceipt.event_id).where(RegistrationReceipt.user_id == user_id),
        select(EventComment.event_id).where(EventComment.author_id == user_id),
        select(ChatMessage.event_id).where(ChatMessage.author_id == user_id),
        select(EventReaction.event_id).where(EventReaction.user_id == user_id),
        select(EventPersonaVisibility.event_id).where(EventPersonaVisibility.user_id == user_id),
        select(SavedEvent.event_id).where(SavedEvent.user_id == user_id),
        select(ContentReport.event_id).where(
            or_(ContentReport.reporter_id == user_id, ContentReport.subject_user_id == user_id)
        ),
        select(ContentHide.event_id).where(ContentHide.user_id == user_id),
        select(Notification.event_id).where(Notification.user_id == user_id, Notification.event_id.is_not(None)),
    )
    for query in event_queries:
        event_ids.update(db.scalars(query).all())

    if event_ids:
        org_ids.update(db.scalars(select(Event.org_id).where(Event.id.in_(event_ids))).all())
    org_ids.discard(None)
    event_ids.discard(None)
    return org_ids, event_ids


def _lock_admins(db: Session) -> list[User]:
    return list(db.scalars(
        select(User)
        .where(User.active.is_(True), User.platform_admin.is_(True))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))


def _lock_request_context(db: Session, user_id: str) -> tuple[User, list[OrgMembership], list[User]]:
    org_ids, _ = _account_scope_ids(db, user_id)
    if org_ids:
        list(db.scalars(
            select(Organization)
            .where(Organization.id.in_(org_ids))
            .order_by(Organization.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ))
    memberships = list(db.scalars(
        select(OrgMembership)
        .where(OrgMembership.user_id == user_id)
        .order_by(OrgMembership.org_id, OrgMembership.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    admins = _lock_admins(db)
    user = next((row for row in admins if row.id == user_id), None)
    if user is None:
        user = db.scalar(
            select(User).where(User.id == user_id).with_for_update()
            .execution_options(populate_existing=True)
        )
    if user is None:
        raise DomainError("authentication_required", "Authentication could not be verified.", 401)
    return user, memberships, admins


def _lock_account_scope(
    db: Session, user_id: str
) -> tuple[User | None, list[OrgMembership], list[OwnershipTransfer], list[MembershipApplication],
           list[MembershipInvitation], dict[str, Event], list[User]]:
    org_ids, event_ids = _account_scope_ids(db, user_id)
    if org_ids:
        list(db.scalars(
            select(Organization)
            .where(Organization.id.in_(org_ids))
            .order_by(Organization.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ))

    transfers = list(db.scalars(
        select(OwnershipTransfer)
        .where(
            OwnershipTransfer.status == "pending",
            or_(OwnershipTransfer.from_user_id == user_id, OwnershipTransfer.nominee_id == user_id),
        )
        .order_by(OwnershipTransfer.org_id, OwnershipTransfer.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    applications = list(db.scalars(
        select(MembershipApplication)
        .where(MembershipApplication.user_id == user_id)
        .order_by(MembershipApplication.org_id, MembershipApplication.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    invitations = list(db.scalars(
        select(MembershipInvitation)
        .where(or_(MembershipInvitation.sender_id == user_id, MembershipInvitation.recipient_id == user_id))
        .order_by(MembershipInvitation.org_id, MembershipInvitation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    memberships = list(db.scalars(
        select(OrgMembership)
        .where(OrgMembership.user_id == user_id)
        .order_by(OrgMembership.org_id, OrgMembership.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    events = list(db.scalars(
        select(Event)
        .where(Event.id.in_(event_ids))
        .order_by(Event.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )) if event_ids else []

    admins = _lock_admins(db)
    user = next((row for row in admins if row.id == user_id), None)
    if user is None:
        user = db.scalar(
            select(User).where(User.id == user_id).with_for_update()
            .execution_options(populate_existing=True)
        )

    current_org_ids, current_event_ids = _account_scope_ids(db, user_id)
    if not current_org_ids.issubset(org_ids) or not current_event_ids.issubset(event_ids):
        raise _RetryErasureScope
    return user, memberships, transfers, applications, invitations, {event.id: event for event in events}, admins


def _blocker(user: User, memberships: list[OrgMembership], admins: list[User]) -> str | None:
    if any(row.active and row.role == "owner" for row in memberships):
        return _OWNER_BLOCKER
    if user.active and user.platform_admin and len(admins) <= 1:
        return _ADMIN_BLOCKER
    return None


def _receipt_result(receipt: ErasureRequest) -> dict[str, Any]:
    return {
        "id": receipt.id,
        "requested_at": receipt.requested_at,
        "due_at": receipt.due_at,
        "completed_at": receipt.completed_at,
        "status": receipt.status,
        "blocker_code": receipt.blocker_code,
        "counts": ({key: int(value) for key, value in (receipt.counts or {}).items()
                    if isinstance(value, int) and not isinstance(value, bool)}
                   if receipt.status == "completed" else {}),
    }


def request_erasure(db: Session, actor: Actor) -> ErasureRequest:
    user_id = _uuid(actor.user_id)
    user, memberships, admins = _lock_request_context(db, user_id)
    if not user.active or db.get(ErasedAccount, user_id) is not None:
        raise DomainError("authentication_required", "Authentication could not be verified.", 401)

    existing = db.scalar(
        select(ErasureRequest)
        .where(ErasureRequest.user_id == user_id, ErasureRequest.status != "completed")
        .order_by(ErasureRequest.requested_at.desc(), ErasureRequest.id)
        .with_for_update()
    )
    if existing is not None:
        if existing.status in {"pending", "blocked"} and existing.blocker_code not in _PROVIDER_CODES:
            existing.blocker_code = _blocker(user, memberships, admins)
            existing.status = "blocked" if existing.blocker_code else "pending"
        return existing

    timestamp = now()
    blocker = _blocker(user, memberships, admins)
    receipt = ErasureRequest(
        user_id=user_id,
        requested_at=timestamp,
        due_at=timestamp + ERASURE_DELAY,
        status="blocked" if blocker else "pending",
        blocker_code=blocker,
        counts={},
    )
    db.add(receipt)
    db.flush()
    return receipt


def _scrub_user(user: User) -> None:
    user.email = f"erased-{user.id}@example.invalid"
    user.email_verified = False
    user.active = False
    user.platform_admin = False
    user.nickname = None
    user.age_bracket = None
    user.tags = []
    user.pronouns = None
    user.icebreaker = None
    user.persona_visible = False


def _held_content(db: Session, at: datetime, *, kind: str, target_ids: set[str]) -> set[str]:
    if not target_ids:
        return set()
    return set(db.scalars(
        select(ContentReport.target_id).where(
            ContentReport.kind == kind,
            ContentReport.target_id.in_(target_ids),
            ContentReport.status.in_(("open", "escalated")),
            ContentReport.deadline > at,
        )
    ).all())


def purge_erased_content(db: Session, at: datetime | None = None, limit: int = 100) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 100:
        raise ValueError("Erased content purge limit must be between 0 and 100.")
    if limit == 0:
        return 0
    timestamp = at or now()
    comment_held = exists(select(ContentReport.id).where(
        ContentReport.kind == "comment",
        ContentReport.target_id == EventComment.id,
        ContentReport.status.in_(("open", "escalated")),
        ContentReport.deadline > timestamp,
    )).correlate(EventComment)
    message_held = exists(select(ContentReport.id).where(
        ContentReport.kind == "message",
        ContentReport.target_id == ChatMessage.id,
        ContentReport.status.in_(("open", "escalated")),
        ContentReport.deadline > timestamp,
    )).correlate(ChatMessage)
    candidates = union(
        select(EventComment.event_id.label("event_id"))
        .join(ErasedAccount, ErasedAccount.user_id == EventComment.author_id)
        .where(EventComment.body.is_not(None), ~comment_held),
        select(ChatMessage.event_id.label("event_id"))
        .join(ErasedAccount, ErasedAccount.user_id == ChatMessage.author_id)
        .where(ChatMessage.body.is_not(None), ~message_held),
    ).subquery()
    event_ids = list(db.scalars(
        select(candidates.c.event_id).order_by(candidates.c.event_id).limit(limit)
    ))
    if not event_ids:
        return 0

    locked_event_ids = list(db.scalars(
        select(Event.id)
        .where(Event.id.in_(event_ids))
        .order_by(Event.id)
        .with_for_update(skip_locked=True)
    ))
    if not locked_event_ids:
        return 0

    comments = list(db.scalars(
        select(EventComment)
        .join(ErasedAccount, ErasedAccount.user_id == EventComment.author_id)
        .where(
            EventComment.event_id.in_(locked_event_ids),
            EventComment.body.is_not(None),
            ~comment_held,
        )
        .order_by(EventComment.event_id, EventComment.id)
        .limit(limit)
        .with_for_update(of=EventComment, skip_locked=True)
        .execution_options(populate_existing=True)
    ))
    for comment in comments:
        comment.body = None
        comment.removed_at = timestamp
        comment.body_hash = _ERASED_BODY_HASH
        comment.client_key = f"erased-{comment.id}"

    remaining = limit - len(comments)
    messages = []
    if remaining:
        messages = list(db.scalars(
            select(ChatMessage)
            .join(ErasedAccount, ErasedAccount.user_id == ChatMessage.author_id)
            .where(
                ChatMessage.event_id.in_(locked_event_ids),
                ChatMessage.body.is_not(None),
                ~message_held,
            )
            .order_by(ChatMessage.event_id, ChatMessage.id)
            .limit(remaining)
            .with_for_update(of=ChatMessage, skip_locked=True)
            .execution_options(populate_existing=True)
        ))
    for message in messages:
        message.body = None
        message.removed_at = timestamp
        message.body_hash = _ERASED_BODY_HASH
        message.client_key = f"erased-{message.id}"

    purged = len(comments) + len(messages)
    if purged:
        db.flush()
    return purged


def _deidentify_comments_and_chat(
    db: Session, user_id: str, at: datetime
) -> tuple[int, int, int, int]:
    comments = list(db.scalars(
        select(EventComment).where(EventComment.author_id == user_id).order_by(EventComment.id)
    ))
    messages = list(db.scalars(
        select(ChatMessage).where(ChatMessage.author_id == user_id).order_by(ChatMessage.id)
    ))
    held_comments = _held_content(db, at, kind="comment", target_ids={row.id for row in comments})
    held_messages = _held_content(db, at, kind="message", target_ids={row.id for row in messages})

    comment_holds = message_holds = 0
    for comment in comments:
        if comment.id in held_comments and comment.body is not None and comment.removed_at is None:
            comment_holds += 1
        else:
            comment.body = None
            comment.removed_at = comment.removed_at or at
            comment.body_hash = _ERASED_BODY_HASH
        comment.client_key = f"erased-{comment.id}"

    for message in messages:
        if message.id in held_messages and message.body is not None and message.removed_at is None:
            message_holds += 1
        else:
            message.body = None
            message.removed_at = message.removed_at or at
            message.body_hash = _ERASED_BODY_HASH
        message.client_key = f"erased-{message.id}"
    return len(comments) - comment_holds, comment_holds, len(messages) - message_holds, message_holds


def _apply_local_erasure(
    db: Session,
    user_id: str,
    at: datetime,
    *,
    user: User | None,
    memberships: list[OrgMembership],
    transfers: list[OwnershipTransfer],
    applications: list[MembershipApplication],
    invitations: list[MembershipInvitation],
    events: dict[str, Event],
) -> dict[str, int]:
    if user is None:
        user = User(
            id=user_id,
            email=f"erased-{user_id}@example.invalid",
            email_verified=False,
            active=False,
            platform_admin=False,
            nickname=None,
            age_bracket=None,
            tags=[],
            pronouns=None,
            icebreaker=None,
            persona_visible=False,
            created_at=at,
        )
        db.add(user)
        db.flush()
    _scrub_user(user)
    db.flush()

    registrations_cancelled = 0
    registrations_preserved = 0
    for event_id, event in events.items():
        while _drain_event_locked(db, event, limit=DRAIN_BATCH_SIZE) >= DRAIN_BATCH_SIZE:
            pass
        catch_up_locked(db, event, at)
        rows = list(db.scalars(
            select(Registration)
            .where(Registration.event_id == event_id, Registration.user_id == user_id,
                   Registration.status.in_(ACTIVE_STATUSES))
            .order_by(Registration.admission_order, Registration.id)
            .with_for_update()
        ))
        if event.starts_at is not None and event.starts_at > at:
            released_seat = False
            for registration in rows:
                released_seat = released_seat or registration.status in SEAT_STATUSES
                registration.status = "cancelled"
                registration.updated_at = at
                registration.persona_shared = False
                _clear_review(registration)
                _clear_reconfirmation(registration)
                registrations_cancelled += 1
            if released_seat:
                _promote_open_seats_locked(db, event, at)
        else:
            for registration in rows:
                registration.persona_shared = False
            registrations_preserved += len(rows)

    memberships_deactivated = sum(row.active is True for row in memberships)
    for row in memberships:
        row.active = False
    applications_withdrawn = 0
    for row in applications:
        row.persona_shared = False
        if row.status == "pending":
            row.status = "withdrawn"
            row.resolved_at = at
            row.reason = None
            applications_withdrawn += 1
    invitations_revoked = 0
    for row in invitations:
        if row.status == "pending":
            row.status = "revoked"
            row.resolved_at = at
            invitations_revoked += 1
    transfers_revoked = 0
    for row in transfers:
        if row.status == "pending":
            row.status = "revoked"
            row.version += 1
            row.resolved_at = at
            row.decided_by = None
            db.add(OwnershipTransferAudit(
                transfer_id=row.id,
                actor_id=None,
                action="revoked",
                created_at=at,
            ))
            transfers_revoked += 1

    event_reaction_count = int(db.scalar(select(func.count()).select_from(EventReaction)
                                           .where(EventReaction.user_id == user_id)) or 0)
    interested = db.execute(
        select(EventReaction.event_id, func.count())
        .where(EventReaction.user_id == user_id, EventReaction.kind == "interested")
        .group_by(EventReaction.event_id)
    ).all()
    for event_id, count in interested:
        event = events.get(event_id)
        if event is not None:
            event.interest_count = max(0, (event.interest_count or 0) - int(count))
    db.execute(delete(EventReaction).where(EventReaction.user_id == user_id))

    comments_scrubbed, comments_held, messages_scrubbed, messages_held = _deidentify_comments_and_chat(
        db, user_id, at
    )
    private_rows_removed = 0
    for model in (UserPreferences, UserDiscoveryPreferences, SavedEvent, EventPersonaVisibility):
        predicate = model.user_id == user_id
        result = db.execute(delete(model).where(predicate))
        private_rows_removed += int(result.rowcount or 0)
    result = db.execute(delete(UserBlock).where(or_(
        UserBlock.blocker_id == user_id, UserBlock.target_id == user_id,
    )))
    private_rows_removed += int(result.rowcount or 0)
    result = db.execute(delete(ContentHide).where(ContentHide.user_id == user_id))
    private_rows_removed += int(result.rowcount or 0)
    result = db.execute(delete(AnnouncementReaction).where(AnnouncementReaction.user_id == user_id))
    reactions_removed = event_reaction_count + int(result.rowcount or 0)
    result = db.execute(delete(Notification).where(Notification.user_id == user_id))
    private_rows_removed += int(result.rowcount or 0)
    result = db.execute(delete(RegistrationReceipt).where(RegistrationReceipt.user_id == user_id))
    private_rows_removed += int(result.rowcount or 0)

    tombstone = db.get(ErasedAccount, user_id)
    if tombstone is None:
        db.add(ErasedAccount(user_id=user_id, erased_at=at))
    elif tombstone.erased_at < at:
        tombstone.erased_at = at
    return {
        "registrations_cancelled": registrations_cancelled,
        "registrations_preserved": registrations_preserved,
        "comments_deidentified": comments_scrubbed,
        "comments_held": comments_held,
        "messages_deidentified": messages_scrubbed,
        "messages_held": messages_held,
        "reactions_removed": reactions_removed,
        "private_rows_removed": private_rows_removed,
        "memberships_deactivated": memberships_deactivated,
        "applications_withdrawn": applications_withdrawn,
        "invitations_revoked": invitations_revoked,
        "ownership_transfers_revoked": transfers_revoked,
    }


def _provider_configuration(settings) -> tuple[str, str] | None:
    url = getattr(settings, "supabase_url", None)
    secret = getattr(settings, "supabase_storage_secret", None)
    if (not isinstance(url, str) or not re.fullmatch(r"https://[a-z0-9-]{8,64}\.supabase\.co", url)
            or not isinstance(secret, str)
            or not re.fullmatch(r"sb_secret_[A-Za-z0-9_-]{10,256}", secret)):
        return None
    return url, secret


def _delete_supabase_user(user_id: str, settings) -> None:
    configuration = _provider_configuration(settings)
    if configuration is None:
        raise _ProviderFailure
    base_url, secret = configuration
    request = Request(
        f"{base_url}/auth/v1/admin/users/{user_id}",
        headers={"apikey": secret, "Accept": "application/json"},
        method="DELETE",
    )
    try:
        with build_opener(_NoRedirectHandler()).open(request, timeout=5) as response:
            status = getattr(response, "status", None) or response.getcode()
        if status not in {200, 204}:
            raise _ProviderFailure
    except HTTPError as error:
        status = error.code
        error.close()
        if status != 404:
            raise _ProviderFailure from None
    except (HTTPException, URLError, TimeoutError, OSError):
        raise _ProviderFailure from None


def _load_receipt(factory, receipt_id: str) -> dict[str, Any]:
    with factory.begin() as db:
        _set_fulfillment_timeouts(db)
        receipt = db.get(ErasureRequest, receipt_id)
        if receipt is None:
            raise DomainError("erasure_request_not_found", "The erasure request was not found.", 404)
        return _receipt_result(receipt)


def _set_receipt_state(factory, receipt_id: str, *, status: str, blocker_code: str | None) -> dict[str, Any]:
    with factory.begin() as db:
        _set_fulfillment_timeouts(db)
        receipt = db.scalar(select(ErasureRequest).where(ErasureRequest.id == receipt_id).with_for_update())
        if receipt is None:
            raise DomainError("erasure_request_not_found", "The erasure request was not found.", 404)
        if receipt.status != "completed":
            receipt.status = status
            receipt.blocker_code = blocker_code
    return _load_receipt(factory, receipt_id)


def _complete_receipt(factory, receipt_id: str, at: datetime) -> dict[str, Any]:
    with factory.begin() as db:
        _set_fulfillment_timeouts(db)
        receipt = db.scalar(select(ErasureRequest).where(ErasureRequest.id == receipt_id).with_for_update())
        if receipt is None:
            raise DomainError("erasure_request_not_found", "The erasure request was not found.", 404)
        if receipt.status != "completed":
            receipt.completed_at = at
            receipt.status = "completed"
            receipt.blocker_code = None
            receipt.user_id = None
    return _load_receipt(factory, receipt_id)


def fulfill_erasure(receipt_id: str, *, explicit_provider_action: bool = False) -> dict[str, Any]:
    receipt_id = _uuid(receipt_id)
    factory = session_factory()
    cleanup_done = False
    user_id: str | None = None
    provider_stage: str | None = None

    for attempt in range(_MAX_SCOPE_RETRIES):
        try:
            with factory.begin() as db:
                _set_fulfillment_timeouts(db)
                receipt = db.scalar(
                    select(ErasureRequest).where(ErasureRequest.id == receipt_id).with_for_update()
                )
                if receipt is None:
                    raise DomainError("erasure_request_not_found", "The erasure request was not found.", 404)
                timestamp = now()
                if receipt.status == "completed":
                    return _receipt_result(receipt)
                user_id = receipt.user_id
                if user_id is None:
                    raise DomainError("erasure_request_invalid", "The erasure request cannot be fulfilled.", 409)
                settings = get_settings()
                provider_required = getattr(settings, "auth_provider", "fixture") == "supabase"
                provider_required = provider_required or receipt.blocker_code in _PROVIDER_CODES
                tombstone = db.get(ErasedAccount, user_id)
                if tombstone is not None:
                    cleanup_done = True
                    provider_stage = receipt.blocker_code
                    if provider_required and provider_stage not in _PROVIDER_CODES:
                        receipt.status = "processing"
                        receipt.blocker_code = "provider_revocation_pending"
                        provider_stage = receipt.blocker_code
                    elif not provider_required:
                        receipt.status = "processing"
                        receipt.blocker_code = None
                else:
                    user, memberships, transfers, applications, invitations, events, admins = _lock_account_scope(
                        db, user_id
                    )
                    if user is None or not user.active:
                        blocker = "account_unavailable"
                    else:
                        blocker = _blocker(user, memberships, admins)
                    if blocker is not None:
                        receipt.status = "blocked"
                        receipt.blocker_code = blocker
                        return _receipt_result(receipt)
                    counts = _apply_local_erasure(
                        db,
                        user_id,
                        timestamp,
                        user=user,
                        memberships=memberships,
                        transfers=transfers,
                        applications=applications,
                        invitations=invitations,
                        events=events,
                    )
                    receipt.counts = counts
                    receipt.status = "processing" if provider_required else "completed"
                    receipt.completed_at = None if provider_required else timestamp
                    receipt.blocker_code = "provider_revocation_pending" if provider_required else None
                    if not provider_required:
                        receipt.user_id = None
                    cleanup_done = True
                    provider_stage = receipt.blocker_code
            break
        except _RetryErasureScope:
            if attempt + 1 == _MAX_SCOPE_RETRIES:
                return _set_receipt_state(
                    factory, receipt_id, status="blocked", blocker_code="account_activity_changed"
                )

    if not cleanup_done or user_id is None:
        return _load_receipt(factory, receipt_id)
    try:
        settings = get_settings()
    except (AttributeError, TypeError, ValueError):
        return _set_receipt_state(
            factory, receipt_id, status="blocked", blocker_code="provider_configuration_unavailable"
        )
    provider_required = getattr(settings, "auth_provider", "fixture") == "supabase"
    provider_required = provider_required or provider_stage in _PROVIDER_CODES
    if not provider_required:
        return _complete_receipt(factory, receipt_id, now())
    if provider_stage == "provider_revocation_complete":
        return _complete_receipt(factory, receipt_id, now())
    if not explicit_provider_action:
        return _set_receipt_state(
            factory, receipt_id, status="blocked", blocker_code="provider_action_required"
        )
    if _provider_configuration(settings) is None:
        return _set_receipt_state(
            factory, receipt_id, status="blocked", blocker_code="provider_secret_unavailable"
        )
    try:
        _delete_supabase_user(user_id, settings)
    except _ProviderFailure:
        return _set_receipt_state(
            factory, receipt_id, status="blocked", blocker_code="provider_revocation_failed"
        )
    result = _set_receipt_state(
        factory, receipt_id, status="processing", blocker_code="provider_revocation_complete"
    )
    if result["status"] == "completed":
        return result
    return _complete_receipt(factory, receipt_id, now())


def purge_erasure_receipts(db: Session, at: datetime | None = None, limit: int = 10) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("Receipt purge limit must be between 1 and 100.")
    cutoff = (at or now()) - RECEIPT_RETENTION
    expired_ids = select(ErasureRequest.id).where(
        ErasureRequest.status == "completed",
        ErasureRequest.completed_at.is_not(None),
        ErasureRequest.completed_at <= cutoff,
    ).order_by(ErasureRequest.completed_at, ErasureRequest.id).limit(limit)
    result = db.execute(delete(ErasureRequest).where(ErasureRequest.id.in_(expired_ids)))
    return int(result.rowcount or 0)


def export_tombstones(db: Session) -> list[dict[str, str]]:
    return [
        {"user_id": user_id, "erased_at": erased_at.isoformat()}
        for user_id, erased_at in db.execute(
            select(ErasedAccount.user_id, ErasedAccount.erased_at).order_by(ErasedAccount.user_id)
        )
    ]


def _validate_tombstone(record: Mapping[str, Any]) -> tuple[str, datetime]:
    if set(record) != {"user_id", "erased_at"}:
        raise ValueError("Tombstone records may contain only user_id and erased_at.")
    user_id = record.get("user_id")
    erased_at = record.get("erased_at")
    if not isinstance(user_id, str):
        raise ValueError("Tombstone user_id must be a UUID.")
    try:
        parsed_id = UUID(user_id)
    except ValueError:
        raise ValueError("Tombstone user_id must be a UUID.") from None
    if str(parsed_id) != user_id.casefold():
        raise ValueError("Tombstone user_id must be a canonical UUID.")
    if isinstance(erased_at, str):
        try:
            erased_at = datetime.fromisoformat(erased_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Tombstone erased_at must be an ISO timestamp.") from None
    if (not isinstance(erased_at, datetime) or erased_at.tzinfo is None
            or erased_at.utcoffset() is None):
        raise ValueError("Tombstone erased_at must include a timezone.")
    return str(parsed_id), erased_at.astimezone(timezone.utc)


def _validated_restore_url(db_url: str | None):
    value = db_url if db_url is not None else get_settings().database_url
    try:
        url = make_url(value)
        address = ipaddress.ip_address(url.host or "")
    except (TypeError, ValueError):
        raise ValueError("Erasure replay requires a validated isolated restore database.") from None
    try:
        port = url.port
    except ValueError:
        raise ValueError("Erasure replay requires a validated isolated restore database.") from None
    if (url.drivername != "postgresql+psycopg" or not address.is_loopback or port != 5433
            or not isinstance(url.database, str)
            or not _RESTORE_DATABASE.fullmatch(url.database)
            ):
        raise ValueError("Erasure replay requires a validated isolated restore database.")
    return url


def replay_erasures(records: Iterable[Mapping[str, Any]], db_url: str | None = None) -> dict[str, int]:
    validated_url = _validated_restore_url(db_url)
    if isinstance(records, (str, bytes, Mapping)):
        raise ValueError("Erasure replay expects an iterable of tombstone records.")
    validated = []
    for record in records:
        if len(validated) >= 10_000:
            raise ValueError("Erasure replay batch exceeds its limit.")
        if not isinstance(record, Mapping):
            raise ValueError("Tombstone records must be mappings.")
        validated.append(_validate_tombstone(record))
    target_engine = create_engine(validated_url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
    factory = sessionmaker(target_engine, expire_on_commit=False)
    applied = created = 0
    try:
        for user_id, erased_at in validated:
            try:
                with factory.begin() as db:
                    user, memberships, transfers, applications, invitations, events, _admins = _lock_account_scope(
                        db, user_id
                    )
                    was_missing = user is None
                    counts = _apply_local_erasure(
                        db,
                        user_id,
                        erased_at,
                        user=user,
                        memberships=memberships,
                        transfers=transfers,
                        applications=applications,
                        invitations=invitations,
                        events=events,
                    )
                    request_rows = list(db.scalars(
                        select(ErasureRequest).where(ErasureRequest.user_id == user_id)
                        .order_by(ErasureRequest.requested_at, ErasureRequest.id)
                        .with_for_update()
                    ))
                    for receipt in request_rows:
                        receipt.status = "completed"
                        receipt.blocker_code = None
                        receipt.completed_at = erased_at
                        receipt.user_id = None
                        if not isinstance(receipt.counts, dict):
                            receipt.counts = {}
                        receipt.counts = {
                            key: int(value) for key, value in receipt.counts.items()
                            if isinstance(value, int) and not isinstance(value, bool)
                        }
                    applied += 1
                    created += int(was_missing)
            except SQLAlchemyError:
                raise RuntimeError("Erasure replay failed for the validated restore target.") from None
    finally:
        target_engine.dispose()
    return {"applied": applied, "created_tombstone_users": created}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operator-mediated account erasure")
    subparsers = parser.add_subparsers(dest="action", required=True)
    fulfill_parser = subparsers.add_parser("fulfill", help="fulfill one erasure request")
    fulfill_parser.add_argument("receipt_id")
    fulfill_parser.add_argument(
        "--provider-action",
        action="store_true",
        help="explicitly authorize the configured Supabase Auth admin deletion",
    )
    arguments = parser.parse_args(argv)
    result = fulfill_erasure(
        arguments.receipt_id,
        explicit_provider_action=arguments.provider_action,
    )
    print(json.dumps(result, default=lambda value: value.isoformat() if isinstance(value, datetime) else value))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

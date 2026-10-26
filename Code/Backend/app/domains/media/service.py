from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.communication import require_communication_allowed
from app.core.contracts import Actor
from app.core.event_safety import can_read_event, event_is_terminal, require_mutable_event
from app.core.errors import DomainError
from app.domains.events.models import Event
from app.domains.events.service import draft_version, require_draft_version
from app.domains.organizations.models import Organization
from app.domains.organizations.service import require_manager
from app.domains.media.codec import NormalizedImage
from app.domains.media.models import MediaAsset
from app.domains.media.schemas import MediaMutationOut
from app.domains.media.storage import MediaQuotaExceeded, MediaStorageError, read_webp, store_webp


def _require_writable_organization(organization: Organization) -> None:
    if organization.accreditation_status == "rejected":
        raise DomainError(
            "organization_read_only",
            "Rejected organizations cannot change media.",
            403,
        )


def _event_or_404(db: Session, event_id: str) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise DomainError("event_not_found", "Event was not found.", 404)
    return event


def authorize_banner_upload(db: Session, actor: Actor, event_id: str) -> None:
    event = _event_or_404(db, event_id)
    organization = require_manager(db, actor, event.org_id)
    _require_writable_organization(organization)
    require_mutable_event(db, event)
    if event.status != "draft":
        raise DomainError("published_event_immutable", "Published events cannot be edited.", 409)
    require_communication_allowed(db, actor.user_id)


def authorize_logo_upload(db: Session, actor: Actor, org_id: str) -> None:
    organization = require_manager(db, actor, org_id)
    _require_writable_organization(organization)
    require_communication_allowed(db, actor.user_id)


def _locked_event(db: Session, actor: Actor, event_id: str) -> tuple[Organization, Event]:
    initial = _event_or_404(db, event_id)
    organization = require_manager(db, actor, initial.org_id, lock=True)
    _require_writable_organization(organization)
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None or event.org_id != organization.id:
        raise DomainError("event_not_found", "Event was not found.", 404)
    # Recheck the manager grant after both rows have been serialized.
    require_manager(db, actor, organization.id)
    _require_writable_organization(organization)
    require_mutable_event(db, event)
    if event.status != "draft":
        raise DomainError("published_event_immutable", "Published events cannot be edited.", 409)
    return organization, event


def _require_if_match(if_match: str | None) -> None:
    if if_match is None:
        raise DomainError("precondition_required", "If-Match is required for event media changes.", 428)


def _media_url(media_id: str) -> str:
    return f"/api/v1/media/{media_id}"


def _store_for_organization(content: bytes, org_id: str) -> str:
    try:
        return store_webp(content, org_id=org_id)
    except MediaQuotaExceeded as error:
        raise DomainError(
            "media_quota_exceeded",
            "The media storage quota has been reached.",
            error.status_code,
        ) from None
    except MediaStorageError:
        raise DomainError("media_storage_unavailable", "Media storage is unavailable.", 503) from None


def _mutation(asset: MediaAsset | None, version: str | None = None) -> MediaMutationOut:
    if asset is None:
        return MediaMutationOut(
            media_url=None, width=None, height=None, byte_size=None, draft_version=version,
        )
    return MediaMutationOut(
        media_url=_media_url(asset.id),
        width=asset.width,
        height=asset.height,
        byte_size=asset.byte_size,
        draft_version=version,
    )


def upload_banner(
    db: Session,
    actor: Actor,
    event_id: str,
    if_match: str | None,
    image: NormalizedImage,
) -> MediaMutationOut:
    organization, event = _locked_event(db, actor, event_id)
    _require_if_match(if_match)
    require_draft_version(event, if_match)
    require_communication_allowed(db, actor.user_id, lock=True)
    media_id = _store_for_organization(image.content, organization.id)
    asset = MediaAsset(
        id=media_id,
        org_id=organization.id,
        kind="banner",
        width=image.width,
        height=image.height,
        byte_size=image.byte_size,
        created_by=actor.user_id,
    )
    db.add(asset)
    db.flush()
    event.banner_media_id = media_id
    if event.banner_key is None:
        event.banner_key = "heritage"
    db.flush()
    return _mutation(asset, draft_version(event))


def remove_banner(
    db: Session,
    actor: Actor,
    event_id: str,
    if_match: str | None,
) -> MediaMutationOut:
    _organization, event = _locked_event(db, actor, event_id)
    _require_if_match(if_match)
    require_draft_version(event, if_match)
    require_communication_allowed(db, actor.user_id, lock=True)
    event.banner_media_id = None
    db.flush()
    return _mutation(None, draft_version(event))


def upload_logo(
    db: Session,
    actor: Actor,
    org_id: str,
    image: NormalizedImage,
) -> MediaMutationOut:
    organization = require_manager(db, actor, org_id, lock=True)
    _require_writable_organization(organization)
    require_manager(db, actor, org_id)
    require_communication_allowed(db, actor.user_id, lock=True)
    media_id = _store_for_organization(image.content, organization.id)
    asset = MediaAsset(
        id=media_id,
        org_id=organization.id,
        kind="logo",
        width=image.width,
        height=image.height,
        byte_size=image.byte_size,
        created_by=actor.user_id,
    )
    db.add(asset)
    db.flush()
    organization.logo_media_id = media_id
    db.flush()
    return _mutation(asset)


def remove_logo(db: Session, actor: Actor, org_id: str) -> MediaMutationOut:
    organization = require_manager(db, actor, org_id, lock=True)
    _require_writable_organization(organization)
    require_manager(db, actor, org_id)
    require_communication_allowed(db, actor.user_id, lock=True)
    organization.logo_media_id = None
    db.flush()
    return _mutation(None)


def _private_access(db: Session, actor: Actor | None, org_id: str) -> None:
    if actor is None:
        raise DomainError("authentication_required", "Sign in to view this image.", 401)
    require_manager(db, actor, org_id)


def authorize_and_read(db: Session, actor: Actor | None, media_id: str) -> bytes:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise DomainError("media_not_found", "Media was not found.", 404)

    if asset.kind == "logo":
        organization = db.get(Organization, asset.org_id)
        if organization is None or organization.logo_media_id != asset.id:
            raise DomainError("media_not_found", "Media was not found.", 404)
        if organization.accreditation_status != "approved":
            _private_access(db, actor, organization.id)
    elif asset.kind == "banner":
        event = db.scalar(select(Event).where(
            Event.banner_media_id == asset.id,
            Event.org_id == asset.org_id,
        ))
        if event is None:
            raise DomainError("media_not_found", "Media was not found.", 404)
        organization = db.get(Organization, event.org_id)
        if organization is None:
            raise DomainError("media_not_found", "Media was not found.", 404)
        if event_is_terminal(db, event):
            if actor is None:
                raise DomainError("media_not_found", "Media was not found.", 404)
            _private_access(db, actor, organization.id)
        elif event.status != "published" or organization.accreditation_status != "approved":
            _private_access(db, actor, organization.id)
        elif not can_read_event(
            db,
            event,
            viewer_id=actor.user_id if actor is not None else None,
        ):
            raise DomainError("media_not_found", "Media was not found.", 404)
    else:
        raise DomainError("media_not_found", "Media was not found.", 404)

    try:
        content = read_webp(asset.id, db=db)
    except MediaStorageError:
        raise DomainError("media_storage_unavailable", "Media storage is unavailable.", 503) from None
    if content is None:
        raise DomainError("media_not_found", "Media was not found.", 404)
    return content

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import current_actor, optional_actor, require_eligible
from app.core.contracts import Actor
from app.db.session import get_db
from app.domains.announcements import service
from app.domains.announcements.schemas import (
    AnnouncementCreate,
    AnnouncementOut,
    AnnouncementPatch,
    AnnouncementRevisionOut,
)
from app.domains.social.schemas import ReactionInput, ReactionSummary

router = APIRouter()


def _private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


@router.get(
    "/organizations/{org_id}/announcements",
    response_model=list[AnnouncementOut],
)
def get_announcements(
    org_id: UUID,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db, scope="function"),
    actor: Actor | None = Depends(optional_actor),
) -> list[AnnouncementOut]:
    _private_no_store(response)
    return service.list_announcements(db, org_id, actor, limit=limit, offset=offset)


@router.post(
    "/organizations/{org_id}/announcements",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
)
def post_announcement(
    org_id: UUID,
    payload: AnnouncementCreate,
    response: Response,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> AnnouncementOut:
    _private_no_store(response)
    result = service.create_announcement(db, org_id, actor, payload)
    _etag(response, result.version)
    return result


@router.get(
    "/organizations/{org_id}/announcements/manage",
    response_model=list[AnnouncementOut],
)
def get_managed_announcements(
    org_id: UUID,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> list[AnnouncementOut]:
    _private_no_store(response)
    return service.list_managed_announcements(
        db, org_id, actor, limit=limit, offset=offset
    )


@router.get("/announcements/{announcement_id}", response_model=AnnouncementOut)
def get_announcement(
    announcement_id: UUID,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor | None = Depends(optional_actor),
) -> AnnouncementOut:
    _private_no_store(response)
    result = service.get_announcement(db, announcement_id, actor)
    _etag(response, result.version)
    return result


@router.patch("/announcements/{announcement_id}", response_model=AnnouncementOut)
def patch_announcement(
    announcement_id: UUID,
    payload: AnnouncementPatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> AnnouncementOut:
    _private_no_store(response)
    result = service.update_announcement(
        db, announcement_id, actor, payload, if_match
    )
    _etag(response, result.version)
    return result


@router.delete(
    "/announcements/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_announcement(
    announcement_id: UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> None:
    _private_no_store(response)
    result = service.remove_announcement(db, announcement_id, actor, if_match)
    _etag(response, result.version)


@router.get(
    "/announcements/{announcement_id}/history",
    response_model=list[AnnouncementRevisionOut],
)
def get_announcement_history(
    announcement_id: UUID,
    response: Response,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> list[AnnouncementRevisionOut]:
    _private_no_store(response)
    return service.list_announcement_history(db, announcement_id, actor)


@router.get(
    "/announcements/{announcement_id}/reactions",
    response_model=ReactionSummary,
)
def get_announcement_reactions(
    announcement_id: UUID,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor | None = Depends(optional_actor),
) -> ReactionSummary:
    _private_no_store(response)
    return service.get_reaction_summary(db, announcement_id, actor)


@router.post(
    "/announcements/{announcement_id}/reactions",
    response_model=ReactionSummary,
)
def post_announcement_reaction(
    announcement_id: UUID,
    payload: ReactionInput,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> ReactionSummary:
    _private_no_store(response)
    return service.set_reaction(
        db, announcement_id, actor, payload.reaction
    )

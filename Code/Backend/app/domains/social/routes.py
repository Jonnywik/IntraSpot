from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import optional_actor, require_eligible
from app.core.contracts import Actor
from app.core.communication_schemas import ContentCreate, ContentItem, ContentPage
from app.db.models import now
from app.db.session import get_db
from app.domains.social import service
from app.domains.social.schemas import ReactionInput, ReactionSummary


router = APIRouter()


@router.get("/events/{event_id}/reactions", response_model=ReactionSummary)
def get_reactions(
    event_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor | None = Depends(optional_actor),
) -> ReactionSummary:
    return service.get_reaction_summary(db, event_id, actor, at=now())


@router.post("/events/{event_id}/reactions", response_model=ReactionSummary)
def set_reaction(
    event_id: UUID,
    payload: ReactionInput,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> ReactionSummary:
    return service.set_reaction(db, event_id, actor.user_id, payload.reaction)


@router.get("/events/{event_id}/comments", response_model=ContentPage)
def get_comments(
    event_id: UUID,
    before_sequence: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db, scope="function"),
    actor: Actor | None = Depends(optional_actor),
) -> ContentPage:
    return service.list_comments(
        db,
        event_id,
        actor,
        before_sequence=before_sequence,
        limit=limit,
    )


@router.post("/events/{event_id}/comments", response_model=ContentItem)
def post_comment(
    event_id: UUID,
    payload: ContentCreate,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> ContentItem:
    return service.create_comment(db, event_id, actor.user_id, payload)


@router.delete("/events/{event_id}/comments/{comment_id}", response_model=ContentItem)
def remove_comment(
    event_id: UUID,
    comment_id: UUID,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope="function"),
) -> ContentItem:
    return service.delete_comment(db, event_id, comment_id, actor.user_id)

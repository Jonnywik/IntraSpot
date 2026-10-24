from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db
from app.domains.planning.schemas import (
    EventConflictsOut,
    SavedEventOut,
    SavedEventState,
)
from app.domains.planning.service import (
    event_conflicts,
    list_saved_events,
    remove_saved_event,
    save_event,
    saved_event_state,
)


router = APIRouter()


@router.get("/me/saved-events", response_model=list[SavedEventOut])
def get_saved_events(
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return list_saved_events(db, actor.user_id)


@router.get("/me/saved-events/{event_id}", response_model=SavedEventState)
def get_saved_event_state(
    event_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return saved_event_state(db, actor.user_id, str(event_id))


@router.put("/me/saved-events/{event_id}", response_model=SavedEventState)
def put_saved_event(
    event_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return save_event(db, actor.user_id, str(event_id))


@router.delete("/me/saved-events/{event_id}", response_model=SavedEventState)
def delete_saved_event(
    event_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return remove_saved_event(db, actor.user_id, str(event_id))


@router.get(
    "/me/event-conflicts/{event_id}", response_model=EventConflictsOut
)
def get_event_conflicts(
    event_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return event_conflicts(db, actor.user_id, str(event_id))

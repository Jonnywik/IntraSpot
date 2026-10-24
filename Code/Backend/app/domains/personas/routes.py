from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.auth import require_eligible
from app.core.contracts import Actor
from app.db.session import get_db
from app.domains.personas import service
from app.domains.personas.schemas import PersonaOut, PersonaVisibilityInput, PersonaVisibilityOut, UserBlockOut


router = APIRouter(tags=['personas'])


@router.get('/events/{event_id}/personas/{user_id}', response_model=PersonaOut)
def get_event_persona(
    event_id: UUID,
    user_id: UUID,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope='function'),
):
    return service.get_event_persona(db, event_id, user_id, actor.user_id)


@router.get('/events/{event_id}/persona-visibility', response_model=PersonaVisibilityOut)
def get_event_persona_visibility(
    event_id: UUID,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope='function'),
):
    return service.get_event_visibility(db, event_id, actor.user_id)


@router.put('/events/{event_id}/persona-visibility', response_model=PersonaVisibilityOut)
def put_event_persona_visibility(
    event_id: UUID,
    payload: PersonaVisibilityInput,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope='function'),
):
    return service.set_event_visibility(db, event_id, actor.user_id, payload.visible)


@router.put('/events/{event_id}/blocks/{user_id}', response_model=UserBlockOut)
def put_event_block(
    event_id: UUID,
    user_id: UUID,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope='function'),
):
    return service.block_user(db, event_id, actor.user_id, user_id)


@router.get('/me/blocks', response_model=list[UserBlockOut])
def get_my_blocks(
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope='function'),
):
    return service.list_blocks(db, actor.user_id)


@router.delete('/me/blocks/{user_id}', status_code=204)
def delete_my_block(
    user_id: UUID,
    actor: Actor = Depends(require_eligible),
    db: Session = Depends(get_db, scope='function'),
):
    service.unblock_user(db, actor.user_id, user_id)
    return Response(status_code=204)

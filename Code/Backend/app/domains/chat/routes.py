from fastapi import APIRouter, Depends, Query
from uuid import UUID
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.communication_schemas import ContentCreate, ContentItem
from app.core.contracts import Actor
from app.db.session import get_db
from app.domains.chat import service
from app.domains.chat.schemas import ChatInboxItem, ChatThread

router = APIRouter(tags=['chat'])


@router.get('/me/chats', response_model=list[ChatInboxItem])
def get_my_chats(
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return service.list_chat_inbox(db, actor.user_id)


@router.get('/events/{id}/chat', response_model=ChatThread)
def get_event_chat(
    id: UUID,
    after_sequence: int | None = Query(default=None, ge=1),
    before_sequence: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return service.get_chat_thread(
        db,
        str(id),
        actor.user_id,
        after_sequence=after_sequence,
        before_sequence=before_sequence,
        limit=limit,
        communication_restricted=actor.communication_restricted,
    )


@router.post('/events/{id}/chat/messages', response_model=ContentItem)
def post_event_chat_message(
    id: UUID,
    payload: ContentCreate,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return service.send_chat_message(db, str(id), actor.user_id, payload)

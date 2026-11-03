"""Account-scoped receipt API; fulfilment is never a browser endpoint."""
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db
from app.erasure_models import ErasureRequest

router = APIRouter(prefix='/me/erasure-request', tags=['account erasure'])


class ErasureReceipt(BaseModel):
    id: str
    requested_at: datetime
    due_at: datetime
    completed_at: datetime | None
    status: str
    blocker_code: str | None
    counts: dict[str, int]


@router.get('', response_model=ErasureReceipt | None)
def latest(actor: Actor = Depends(current_actor), db: Session = Depends(get_db, scope='function')):
    return db.scalar(select(ErasureRequest).where(ErasureRequest.user_id == actor.user_id)
                     .order_by(ErasureRequest.requested_at.desc(), ErasureRequest.id).limit(1))


@router.post('', response_model=ErasureReceipt)
def request(actor: Actor = Depends(current_actor), db: Session = Depends(get_db, scope='function')):
    from app.account_erasure import request_erasure
    return request_erasure(db, actor)

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db

from . import service
from .schemas import OwnershipTransferCreate, OwnershipTransferDecision, OwnershipTransferOut


router = APIRouter()


@router.get(
    "/organizations/{org_id}/ownership-transfers",
    response_model=list[OwnershipTransferOut],
)
def list_ownership_transfers(
    org_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return service.list_transfers(db, actor.user_id, str(org_id))


@router.post(
    "/organizations/{org_id}/ownership-transfers",
    response_model=OwnershipTransferOut,
    status_code=201,
)
def create_ownership_transfer(
    org_id: UUID,
    payload: OwnershipTransferCreate,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return service.create_transfer(db, actor.user_id, str(org_id), payload)


@router.post(
    "/organizations/{org_id}/ownership-transfers/{transfer_id}/decision",
    response_model=OwnershipTransferOut,
)
def decide_ownership_transfer(
    org_id: UUID,
    transfer_id: UUID,
    payload: OwnershipTransferDecision,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return service.decide_transfer(
        db,
        actor.user_id,
        str(org_id),
        str(transfer_id),
        payload,
    )

"""Platform-only operational metadata, separate from public readiness."""
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, or_, and_
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.session import get_db
from app.db.models import now
from app.operations_models import MaintenanceState
from app.domains.registrations.models import RegistrationReceipt, Registration

router = APIRouter(prefix='/platform/operations', tags=['operations'])


class MaintenanceView(BaseModel):
    name: str
    last_started_at: datetime | None
    last_success_at: datetime | None
    last_error_code: str | None
    processed_count: int
    duration_ms: int


class OperationsView(BaseModel):
    maintenance: list[MaintenanceView]
    pending_receipts: int
    due_registrations: int


@router.get('', response_model=OperationsView)
def status(actor: Actor = Depends(current_actor), db: Session = Depends(get_db, scope='function')):
    if not actor.platform_admin:
        raise DomainError('platform_admin_required', 'Platform administrator access is required.', 403)
    rows = db.scalars(select(MaintenanceState).order_by(MaintenanceState.name)).all()
    count = db.scalar(select(func.count()).select_from(RegistrationReceipt).where(
        RegistrationReceipt.processed_at.is_(None))) or 0
    at = now()
    due = db.scalar(select(func.count()).select_from(Registration).where(or_(
        and_(Registration.status == 'pending', Registration.review_deadline <= at),
        and_(Registration.status == 'reconfirmation_required', Registration.reconfirm_deadline <= at),
    ))) or 0
    return OperationsView(maintenance=[MaintenanceView.model_validate(row, from_attributes=True) for row in rows],
                          pending_receipts=count, due_registrations=due)

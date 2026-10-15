from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db
from app.domains.moderation.schemas import (
    ContentHideInput,
    ContentHideReceipt,
    ReportCreateInput,
    ReportDecisionInput,
    ReportReceipt,
    ReportReview,
)
from app.domains.moderation.service import (
    create_report,
    decide_report,
    get_moderation_report,
    list_moderation_reports,
    list_my_reports,
    set_content_hide,
)


router = APIRouter()


@router.post('/events/{event_id}/reports', response_model=ReportReceipt, status_code=201)
def submit_report(
    event_id: UUID,
    payload: ReportCreateInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return create_report(
        db,
        actor,
        str(event_id),
        payload.kind,
        str(payload.target_id),
        payload.reason,
    )


@router.get('/me/reports', response_model=list[ReportReceipt])
def my_reports(
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return list_my_reports(db, actor.user_id)


@router.post('/me/content-hides', response_model=ContentHideReceipt)
def update_content_hide(
    payload: ContentHideInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return set_content_hide(
        db,
        actor,
        str(payload.event_id),
        payload.kind,
        str(payload.target_id),
        payload.hidden,
    )


@router.get('/moderation/reports', response_model=list[ReportReview])
def moderation_reports(
    org_id: UUID | None = Query(default=None),
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return list_moderation_reports(db, actor, str(org_id) if org_id is not None else None)


@router.get('/moderation/reports/{report_id}', response_model=ReportReview)
def moderation_report_detail(
    report_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return get_moderation_report(db, actor, str(report_id))


@router.post('/moderation/reports/{report_id}/decision', response_model=ReportReview)
def moderation_report_decision(
    report_id: UUID,
    payload: ReportDecisionInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return decide_report(db, actor, str(report_id), payload.action)

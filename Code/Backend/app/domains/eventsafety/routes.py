from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db
from app.domains.eventsafety import service
from app.domains.eventsafety.schemas import (
    EventReportCreateInput,
    EventReportDecisionInput,
    EventReportReceipt,
    EventReportReview,
    EventSafetyActionInput,
    EventSafetyOut,
    SafetyAuditOut,
    SuspensionActionInput,
    SuspensionOut,
)


router = APIRouter()


def _private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


@router.post(
    "/events/{event_id}/event-reports",
    response_model=EventReportReceipt,
    status_code=status.HTTP_201_CREATED,
)
def submit_event_report(
    event_id: UUID,
    payload: EventReportCreateInput,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    return service.create_event_report(
        db,
        actor,
        str(event_id),
        payload.reason,
        str(payload.client_key),
    )


@router.get("/me/event-reports", response_model=list[EventReportReceipt])
def my_event_reports(
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> list[dict]:
    _private_no_store(response)
    return service.list_my_event_reports(db, actor)


@router.get(
    "/moderation/event-reports", response_model=list[EventReportReview]
)
def event_moderation_reports(
    response: Response,
    org_id: UUID | None = None,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> list[dict]:
    _private_no_store(response)
    return service.list_event_moderation_reports(
        db, actor, org_id=str(org_id) if org_id is not None else None
    )


@router.post(
    "/moderation/event-reports/{report_id}/decision",
    response_model=EventReportReview,
)
def event_moderation_decision(
    report_id: UUID,
    payload: EventReportDecisionInput,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    return service.decide_event_report(
        db,
        actor,
        str(report_id),
        payload.action,
        payload.version,
        payload.event_version,
        str(payload.client_key),
    )


@router.get("/events/{event_id}/safety", response_model=EventSafetyOut)
def event_safety(
    event_id: UUID,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    return service.get_event_safety(db, actor, str(event_id))


@router.post("/events/{event_id}/safety", response_model=EventSafetyOut)
def event_safety_action(
    event_id: UUID,
    payload: EventSafetyActionInput,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    return service.change_event_safety(
        db,
        actor,
        str(event_id),
        payload.action,
        payload.version,
        str(payload.client_key),
    )


@router.get(
    "/organizations/{org_id}/suspension", response_model=SuspensionOut
)
def organization_suspension(
    org_id: UUID,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    return service.get_organization_suspension(db, actor, str(org_id))


@router.post(
    "/organizations/{org_id}/suspension", response_model=SuspensionOut
)
def organization_suspension_action(
    org_id: UUID,
    payload: SuspensionActionInput,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    return service.change_organization_suspension(
        db,
        actor,
        str(org_id),
        payload.action,
        payload.version,
        payload.days,
        str(payload.client_key),
    )


@router.get(
    "/organizations/{org_id}/safety-history",
    response_model=list[SafetyAuditOut],
)
def organization_safety_history(
    org_id: UUID,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> list[dict]:
    _private_no_store(response)
    return service.get_safety_history(db, actor, str(org_id))

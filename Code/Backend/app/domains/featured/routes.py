from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db
from app.domains.featured.schemas import FeaturedDecisionInput, FeaturedRequestOut
from app.domains.featured.service import (
    create_request,
    decide_request,
    list_organization_requests,
    list_platform_requests,
)


router = APIRouter()


@router.post("/events/{event_id}/featured-requests", response_model=FeaturedRequestOut)
def request_featured_event(
    event_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
) -> FeaturedRequestOut:
    return create_request(db, actor, str(event_id))


@router.get(
    "/organizations/{org_id}/featured-requests",
    response_model=list[FeaturedRequestOut],
)
def organization_featured_requests(
    org_id: UUID,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
) -> list[FeaturedRequestOut]:
    return list_organization_requests(db, actor, str(org_id))


@router.get("/platform-admin/featured-requests", response_model=list[FeaturedRequestOut])
def platform_featured_requests(
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
) -> list[FeaturedRequestOut]:
    return list_platform_requests(db, actor, limit)


@router.post(
    "/platform-admin/featured-requests/{request_id}/decisions",
    response_model=FeaturedRequestOut,
)
def decide_featured_request(
    request_id: UUID,
    payload: FeaturedDecisionInput,
    db: Session = Depends(get_db, scope="function"),
    actor: Actor = Depends(current_actor),
) -> FeaturedRequestOut:
    return decide_request(db, actor, str(request_id), payload)

import re
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.session import get_db
from app.domains.announcements.report_schemas import (
    AnnouncementReportCreateInput,
    AnnouncementReportDecisionInput,
    AnnouncementReportReceipt,
    AnnouncementReportReview,
)
from app.domains.announcements.report_service import (
    create_announcement_report,
    decide_announcement_report,
    get_announcement_moderation_report,
    list_announcement_moderation_reports,
    list_my_announcement_reports,
)


router = APIRouter()
_IF_MATCH = re.compile(r'^"([1-9][0-9]*)"$')


def _private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _parse_if_match(value: str | None, *, required: bool) -> int | None:
    if value is None:
        if required:
            raise DomainError(
                "announcement_version_required",
                "A current quoted If-Match version is required.",
                409,
            )
        return None
    match = _IF_MATCH.fullmatch(value)
    # Bound before int conversion; versions are PostgreSQL signed integers.
    if match is None or len(match.group(1)) > 10 or int(match.group(1)) > 2147483647:
        raise DomainError(
            "announcement_version_invalid",
            "If-Match must contain one quoted announcement version.",
            409,
        )
    return int(match.group(1))


@router.post(
    "/announcements/{announcement_id}/reports",
    response_model=AnnouncementReportReceipt,
    status_code=status.HTTP_201_CREATED,
)
def submit_announcement_report(
    announcement_id: UUID,
    response: Response,
    payload: AnnouncementReportCreateInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    return create_announcement_report(
        db, actor, str(announcement_id), payload.reason
    )


@router.get(
    "/me/announcement-reports",
    response_model=list[AnnouncementReportReceipt],
)
def my_announcement_reports(
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> list[dict]:
    _private_no_store(response)
    return list_my_announcement_reports(db, actor.user_id)


@router.get(
    "/moderation/announcement-reports",
    response_model=list[AnnouncementReportReview],
)
def announcement_moderation_reports(
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> list[dict]:
    _private_no_store(response)
    return list_announcement_moderation_reports(db, actor)


@router.get(
    "/moderation/announcement-reports/{report_id}",
    response_model=AnnouncementReportReview,
)
def announcement_moderation_report_detail(
    report_id: UUID,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    result = get_announcement_moderation_report(db, actor, str(report_id))
    _etag(response, result["post_version"])
    return result


@router.post(
    "/moderation/announcement-reports/{report_id}/decision",
    response_model=AnnouncementReportReview,
)
def announcement_moderation_report_decision(
    report_id: UUID,
    payload: AnnouncementReportDecisionInput,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    _private_no_store(response)
    expected_version = _parse_if_match(
        if_match, required=payload.action in {"hide", "restore", "remove"}
    )
    result = decide_announcement_report(
        db,
        actor,
        str(report_id),
        payload.action,
        expected_version=expected_version,
    )
    _etag(response, result["post_version"])
    return result

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


AnnouncementReportReason = Literal['harassment', 'spam', 'deception', 'impersonation', 'other']
AnnouncementReportStatus = Literal['open', 'dismissed', 'hidden', 'restored', 'removed', 'expired']
AnnouncementReportAction = Literal['dismiss', 'hide', 'restore', 'remove', 'expire']
AnnouncementReportDecisionAction = Literal['dismiss', 'hide', 'restore', 'remove']
AnnouncementReportPostState = Literal['visible', 'hidden', 'removed']


class AnnouncementReportCreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reason: AnnouncementReportReason


class AnnouncementReportDecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    action: AnnouncementReportDecisionAction


class AnnouncementReportReceipt(BaseModel):
    id: str
    announcement_id: str
    org_id: str
    status: AnnouncementReportStatus
    deadline: datetime


class AnnouncementReportDecisionAudit(BaseModel):
    id: str
    reviewer_id: str | None
    action: AnnouncementReportAction
    created_at: datetime


class AnnouncementReportReview(AnnouncementReportReceipt):
    reason: AnnouncementReportReason
    reporter_id: str
    subject_user_id: str
    reported_version: int
    evidence: str | None
    decisions: list[AnnouncementReportDecisionAudit]
    post_state: AnnouncementReportPostState
    post_version: int

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ReportKind = Literal['comment', 'message', 'person']
ReportReason = Literal['harassment', 'spam', 'deception', 'impersonation', 'other']
ReportStatus = Literal['open', 'escalated', 'dismissed', 'removed', 'warned', 'expired']
ReportStage = Literal['organization', 'platform']
DecisionAction = Literal['dismiss', 'remove', 'escalate', 'warn']


class ReportCreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: ReportKind
    target_id: UUID
    reason: ReportReason


class ContentHideInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: UUID
    kind: Literal['comment', 'message']
    target_id: UUID
    hidden: bool


class ReportDecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    action: DecisionAction


class ReportReceipt(BaseModel):
    id: str
    event_id: str
    kind: ReportKind
    target_id: str
    status: ReportStatus
    stage: ReportStage
    deadline: datetime


class ContentHideReceipt(BaseModel):
    hidden: bool


class DecisionAudit(BaseModel):
    id: str
    reviewer_id: str | None
    action: Literal['dismiss', 'remove', 'escalate', 'warn', 'expire']
    created_at: datetime


class ReportReview(ReportReceipt):
    org_id: str
    reason: ReportReason
    reporter_id: str
    subject_user_id: str
    evidence: str | None
    decisions: list[DecisionAudit]

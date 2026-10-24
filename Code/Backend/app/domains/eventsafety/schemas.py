from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class SafetyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


EventReportReason = Literal["safety", "deception"]
EventReportStatus = Literal[
    "open", "escalated", "dismissed", "hidden", "removed", "upheld", "expired"
]
EventReportStage = Literal["organization", "platform"]
EventReportAction = Literal["dismiss", "hide", "remove", "uphold"]
EventSafetyAction = Literal["hide", "restore", "remove", "cancel"]
SuspensionAction = Literal["suspend", "resume"]


class EventReportCreateInput(SafetyInput):
    reason: EventReportReason
    client_key: UUID


class EventReportDecisionInput(SafetyInput):
    action: EventReportAction
    version: Annotated[StrictInt, Field(ge=1)]
    event_version: Annotated[StrictInt, Field(ge=0)]
    client_key: UUID


class EventSafetyActionInput(SafetyInput):
    action: EventSafetyAction
    version: Annotated[StrictInt, Field(ge=0)]
    client_key: UUID


class SuspensionActionInput(SafetyInput):
    action: SuspensionAction
    version: Annotated[StrictInt, Field(ge=0)]
    days: Annotated[StrictInt, Field(ge=1, le=30)] | None = None
    client_key: UUID

    @model_validator(mode="after")
    def validate_days_for_action(self):
        if self.action == "resume" and self.days is not None:
            raise ValueError("days must be null when resuming a suspension")
        return self


class EventReportReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_id: str
    org_id: str
    status: EventReportStatus
    stage: EventReportStage
    version: int
    deadline: datetime


class SafetyAuditOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    org_id: str
    event_id: str | None
    report_id: str | None
    actor_id: str | None
    scope: Literal["report", "event", "organization"]
    action: Literal[
        "report", "dismiss", "hide", "restore", "remove", "uphold", "cancel",
        "suspend", "resume", "expire",
    ]
    version: int
    created_at: datetime


class EventReportReview(EventReportReceipt):
    reason: EventReportReason
    evidence: str | None = Field(max_length=4096)
    reporter_id: str
    created_at: datetime
    event_version: int
    decisions: list[SafetyAuditOut]


class EventSafetyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    org_id: str
    org_hidden: bool
    platform_hidden: bool
    removed: bool
    cancelled: bool
    version: int
    registration_available: bool
    can_hide: bool
    can_restore: bool
    can_remove: bool
    can_cancel: bool


class SuspensionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    org_id: str
    version: int
    suspended_until: datetime | None
    is_suspended: bool
    can_manage: bool

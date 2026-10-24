from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.events.schemas import EventPublic


class FeaturedDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject", "revoke"]
    version: int = Field(strict=True, gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Datetime must include a timezone.")
        return value

    @model_validator(mode="after")
    def validate_schedule_fields(self):
        if self.action == "approve":
            if self.ends_at is None:
                raise ValueError("Approval requires an end time.")
        elif "starts_at" in self.model_fields_set or "ends_at" in self.model_fields_set:
            raise ValueError("Schedule fields are only allowed for approval.")
        return self


class FeaturedDecisionOut(BaseModel):
    id: str
    actor_id: str
    action: Literal["requested", "approved", "rejected", "revoked", "paused"]
    created_at: datetime
    starts_at: datetime | None
    ends_at: datetime | None


class FeaturedRequestOut(BaseModel):
    id: str
    event_id: str
    requested_by: str
    requested_at: datetime
    status: Literal["pending", "paused", "approved", "rejected", "revoked", "expired"]
    version: int
    starts_at: datetime | None
    ends_at: datetime | None
    event: EventPublic
    decisions: list[FeaturedDecisionOut]

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


BannerKey = Literal["heritage", "design", "garden", "music"]
SUMMARY_MAX_LENGTH = 200


class EventDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    summary: str = Field(default="", max_length=SUMMARY_MAX_LENGTH)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    venue_name: str | None = Field(default=None, max_length=200)
    venue_address: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, strict=True, gt=0, le=2_147_483_647)
    banner_key: BannerKey | None = None
    cost_label: str = Field(default="Free", max_length=100)
    registration_mode: Literal["instant", "approval"] = "instant"
    review_window_minutes: int | None = Field(default=None, strict=True, ge=15, le=2880)
    event_type: Literal["scheduled"] = "scheduled"

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Datetime must include a timezone.")
        return value


class EventChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime | None = None
    ends_at: datetime | None = None
    venue_name: str | None = Field(default=None, max_length=200)
    venue_address: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, strict=True, gt=0, le=2_147_483_647)
    cost_label: str | None = Field(default=None, max_length=100)
    reconfirm_deadline: datetime
    selection_mode: Literal["exact", "newest_in_pool"] = "exact"
    selected_registration_ids: list[UUID] = Field(default_factory=list)

    @field_validator("starts_at", "ends_at", "reconfirm_deadline")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Datetime must include a timezone.")
        return value


class EventPublic(BaseModel):
    id: str
    org_id: str
    organization_name: str
    title: str
    summary: str
    description: str
    starts_at: datetime
    ends_at: datetime
    venue_name: str
    venue_address: str
    capacity: int
    confirmed_count: int
    reserved_count: int
    remaining_spots: int
    interest_count: int
    banner_key: BannerKey
    cost_label: str
    registration_mode: Literal["instant", "approval"]
    review_window_minutes: int | None
    material_revision: int
    status: Literal["published"]
    published_at: datetime


class EventPrivate(EventPublic):
    title: str | None
    description: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    venue_name: str | None
    venue_address: str | None
    capacity: int | None
    remaining_spots: int | None
    banner_key: BannerKey | None
    status: Literal["draft", "published"]
    published_at: datetime | None
    created_by: str
    created_at: datetime

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.core.discovery import normalized_label


BannerKey = Literal["heritage", "design", "garden", "music"]
EventTag = Annotated[StrictStr, Field(min_length=1, max_length=64)]
SUMMARY_MAX_LENGTH = 200


class EventDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    summary: str = Field(default="", max_length=SUMMARY_MAX_LENGTH)
    tags: list[EventTag] = Field(default_factory=list, max_length=16)
    coarse_area: StrictStr | None = Field(default=None, max_length=80)
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
    event_type: Literal["scheduled", "flash"] = "scheduled"

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Datetime must include a timezone.")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value):
        if not isinstance(value, list):
            return value
        if len(value) > 16:
            raise ValueError("At most 16 event tags are allowed.")
        if any(not isinstance(tag, str) for tag in value):
            raise ValueError("Each event tag must be a string.")
        normalized = [normalized_label(tag) if isinstance(tag, str) else tag for tag in value]
        return list(dict.fromkeys(normalized))

    @field_validator("tags")
    @classmethod
    def validate_normalized_tags(cls, tags: list[str]) -> list[str]:
        if any(not tag or len(tag) > 64 for tag in tags):
            raise ValueError("Each normalized event tag must contain 1 to 64 characters.")
        return tags

    @field_validator("coarse_area", mode="before")
    @classmethod
    def normalize_coarse_area(cls, value):
        if value is None or not isinstance(value, str):
            return value
        normalized = normalized_label(value)
        if len(normalized) > 80:
            raise ValueError("The normalized coarse area must be at most 80 characters.")
        return normalized or None


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
    tags: list[str] = Field(default_factory=list)
    coarse_area: str | None = None
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
    event_type: Literal["scheduled", "flash"] = "scheduled"
    material_revision: int
    status: Literal["published"]
    published_at: datetime
    recommendation_reasons: list[
        Literal["club", "flash", "interests", "area", "availability"]
    ] = Field(default_factory=list)


class EventPrivate(EventPublic):
    draft_version: str = Field(description="Content version for conditional draft saves and publishing.")
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


class EventReviewSummary(EventPublic):
    pending_registration_count: int
    next_review_deadline: datetime | None

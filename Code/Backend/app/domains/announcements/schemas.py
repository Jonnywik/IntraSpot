from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnnouncementAudience = Literal["public", "members"]
AnnouncementState = Literal["visible", "hidden", "removed"]
AnnouncementRevisionAction = Literal["publish", "edit", "remove", "hide", "restore"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _trim_required_text(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
    return value


class AnnouncementCreate(InputModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    audience: AnnouncementAudience
    client_key: UUID

    @field_validator("title", "body", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return _trim_required_text(value)


class AnnouncementPatch(InputModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    audience: AnnouncementAudience | None = None

    @field_validator("title", "body", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field is required when supplied.")
        return _trim_required_text(value)

    @field_validator("audience", mode="before")
    @classmethod
    def require_audience_when_supplied(cls, value: object) -> object:
        if value is None:
            raise ValueError("Audience cannot be null.")
        return value


class AnnouncementOut(BaseModel):
    id: str
    org_id: str
    organization_name: str
    title: str
    body: str | None
    audience: AnnouncementAudience
    version: int
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None
    state: AnnouncementState


class AnnouncementRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    actor_id: str
    action: AnnouncementRevisionAction
    title: str
    body: str | None
    audience: AnnouncementAudience
    created_at: datetime

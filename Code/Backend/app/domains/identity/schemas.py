from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


Tag = Annotated[str, Field(min_length=1, max_length=64)]


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    age_bracket: str | None = Field(default=None, min_length=1, max_length=32)
    tags: list[Tag] = Field(default_factory=list, max_length=32)
    pronouns: str | None = Field(default=None, min_length=1, max_length=40)
    icebreaker: str | None = Field(default=None, min_length=1, max_length=300)
    persona_visible: StrictBool = False

    @field_validator("tags")
    @classmethod
    def tags_must_not_be_blank(cls, tags: list[str]) -> list[str]:
        normalized = [tag.strip() for tag in tags]
        if any(not tag for tag in normalized):
            raise ValueError("Tags must not be blank.")
        return normalized


class ProfileResponse(BaseModel):
    nickname: str | None
    age_bracket: str | None
    tags: list[str]
    pronouns: str | None
    icebreaker: str | None
    persona_visible: bool


class OrgGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_id: str
    org_name: str
    role: str
    accreditation_status: str


class MeResponse(BaseModel):
    id: str
    nickname: str | None
    eligible: bool
    profile_complete: bool
    platform_admin: bool
    grants: list[OrgGrantResponse]
    communication_restricted: bool = False

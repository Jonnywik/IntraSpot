from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictBool


class PersonaOut(BaseModel):
    nickname: str | None
    age_bracket: str | None
    tags: list[str]
    pronouns: str | None
    icebreaker: str | None


class PersonaVisibilityInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    visible: StrictBool


class PersonaVisibilityOut(BaseModel):
    visible: bool
    expires_at: datetime


class UserBlockOut(BaseModel):
    user_id: str
    created_at: datetime

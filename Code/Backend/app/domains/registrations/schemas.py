from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt


class RegistrationInput(BaseModel):
    model_config = {'extra': 'forbid'}

    persona_shared: StrictBool = False


class RegistrationDecisionInput(BaseModel):
    model_config = {'extra': 'forbid'}

    decision: Literal['approve', 'reject']


class RegistrationReconfirmationInput(BaseModel):
    model_config = {'extra': 'forbid'}

    accept: StrictBool
    revision: StrictInt = Field(ge=1)


class RegistrationResult(BaseModel):
    id: str
    event_id: str
    status: Literal[
        'confirmed',
        'waitlisted',
        'pending',
        'reconfirmation_required',
        'cancelled',
        'rejected',
    ]
    waitlist_position: int | None
    waitlist_message: str | None
    admission_order: int
    review_deadline: datetime | None = None
    review_stage: int | None = None
    reviewer_id: str | None = None
    first_reviewer_id: str | None = None
    timeout_count: int = 0
    from_waitlist: bool = False
    persona_shared: bool = False
    reconfirm_deadline: datetime | None = None
    reconfirm_revision: int | None = None


class RegistrationPersona(BaseModel):
    nickname: str | None
    age_bracket: str | None
    tags: list[str]
    pronouns: str | None
    icebreaker: str | None


class RegistrationReview(BaseModel):
    registration: RegistrationResult
    user_id: str
    persona: RegistrationPersona | None


class MyRegistration(RegistrationResult):
    event_title: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    organization_name: str
    is_past: bool

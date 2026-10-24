from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class AttendanceSessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_open: StrictBool
    version: StrictInt = Field(ge=0)
    client_key: UUID


class AttendanceMarkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attended: StrictBool
    version: StrictInt = Field(ge=0)
    client_key: UUID


class AttendanceAttendeeOut(BaseModel):
    registration_id: str
    participant_label: str
    attended: bool


class AttendanceOut(BaseModel):
    event_id: str
    is_open: bool
    version: int
    writable: bool
    confirmed_count: int
    checked_in_count: int
    attendees: list[AttendanceAttendeeOut]


class AttendanceAuditOut(BaseModel):
    id: str
    event_id: str
    actor_id: str
    action: Literal["session", "mark"]
    registration_id: str | None
    previous_value: bool
    value: bool
    version: int
    created_at: datetime


class AttendanceMutationOut(BaseModel):
    event_id: str
    registration_id: str | None
    is_open: bool
    attended: bool | None
    version: int
    recorded_at: datetime

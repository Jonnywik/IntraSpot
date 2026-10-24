from datetime import datetime

from pydantic import BaseModel

from app.domains.events.schemas import EventPublic


class SavedEventOut(BaseModel):
    event_id: str
    saved_at: datetime
    event: EventPublic | None


class SavedEventState(BaseModel):
    event_id: str
    saved: bool
    saved_at: datetime | None


class ConflictEvent(BaseModel):
    event_id: str
    title: str
    organization_name: str
    starts_at: datetime
    ends_at: datetime


class EventConflictsOut(BaseModel):
    event_id: str
    conflicts: list[ConflictEvent]

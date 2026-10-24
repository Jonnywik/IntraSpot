"""One safe content projection shared by comments and confirmed-attendee chat."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID


class ContentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=2000)
    client_key: UUID

    @field_validator('body')
    @classmethod
    def nonblank_body(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Enter a message.')
        return value.strip()


class ContentItem(BaseModel):
    id: str
    event_id: str
    author_id: str
    author_label: str
    sequence: int
    body: str | None
    created_at: datetime
    removed: bool
    locally_hidden: bool
    mine: bool


class ContentPage(BaseModel):
    items: list[ContentItem]
    next_before: int | None = None
    author_labels: dict[str, str] = Field(default_factory=dict)

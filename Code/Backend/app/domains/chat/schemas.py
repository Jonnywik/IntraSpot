from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.communication_schemas import ContentCreate, ContentItem, ContentPage


ChatStatus = Literal['active', 'archived']


class ChatInboxItem(BaseModel):
    event_id: str
    event_title: str
    organization_name: str
    ends_at: datetime
    deletes_at: datetime
    status: ChatStatus
    latest_at: datetime | None


class ChatThread(BaseModel):
    event_id: str
    event_title: str
    status: ChatStatus
    deletes_at: datetime
    can_send: bool
    items: list[ContentItem]
    next_before: int | None = None
    removed_ids: list[str] = Field(default_factory=list)
    author_labels: dict[str, str] = Field(default_factory=dict)


__all__ = ['ChatInboxItem', 'ChatThread', 'ContentCreate', 'ContentItem', 'ContentPage']

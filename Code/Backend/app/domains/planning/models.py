from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now
from app.db.session import Base


class SavedEvent(Base):
    __tablename__ = "saved_events"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id"), primary_key=True
    )
    saved_at: Mapped[datetime] = mapped_column(
        UTC, nullable=False, default=now
    )

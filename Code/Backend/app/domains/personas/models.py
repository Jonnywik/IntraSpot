from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now
from app.db.session import Base


class UserBlock(Base):
    __tablename__ = 'user_blocks'
    __table_args__ = (
        CheckConstraint('blocker_id <> target_id', name='ck_user_blocks_not_self'),
        Index('ix_user_blocks_target_blocker', 'target_id', 'blocker_id'),
    )

    blocker_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    target_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)


class EventPersonaVisibility(Base):
    __tablename__ = 'event_persona_visibility'

    event_id: Mapped[str] = mapped_column(ForeignKey('events.id'), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text('false'),
    )

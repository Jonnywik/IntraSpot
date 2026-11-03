"""Minimal erasure receipts and non-login tombstones for restore replay."""
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class ErasureRequest(Base):
    __tablename__ = 'erasure_requests'
    __table_args__ = (Index('uq_erasure_requests_active_user', 'user_id', unique=True,
                           postgresql_where=text("user_id IS NOT NULL AND status <> 'completed'")),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)
    due_at: Mapped[datetime] = mapped_column(UTC, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTC)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    blocker_code: Mapped[str | None] = mapped_column(String(80))
    counts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class ErasedAccount(Base):
    __tablename__ = 'erased_accounts'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    erased_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)

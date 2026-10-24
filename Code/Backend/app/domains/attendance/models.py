from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_attendance_sessions_version"),
    )

    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class AttendanceMark(Base):
    __tablename__ = "attendance_marks"

    registration_id: Mapped[str] = mapped_column(ForeignKey("registrations.id"), primary_key=True)
    attended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


class AttendanceAudit(Base):
    __tablename__ = "attendance_audits"
    __table_args__ = (
        CheckConstraint("action IN ('session', 'mark')", name="ck_attendance_audits_action"),
        CheckConstraint("version > 0", name="ck_attendance_audits_version"),
        UniqueConstraint("actor_id", "client_key", name="uq_attendance_audits_actor_key"),
        Index("ix_attendance_audits_event_created", "event_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    client_key: Mapped[str] = mapped_column(String(36), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    registration_id: Mapped[str | None] = mapped_column(ForeignKey("registrations.id"), nullable=True)
    previous_value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

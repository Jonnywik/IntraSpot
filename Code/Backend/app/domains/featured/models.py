from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import UTC, now, uid
from app.db.session import Base


class FeaturedRequest(Base):
    __tablename__ = "featured_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','paused','approved','rejected','revoked','expired')",
            name="ck_featured_requests_status",
        ),
        CheckConstraint("version > 0", name="ck_featured_requests_version"),
        CheckConstraint(
            "status != 'approved' OR "
            "(starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at)",
            name="ck_featured_requests_window",
        ),
        Index(
            "uq_featured_requests_open_event",
            "event_id",
            unique=True,
            postgresql_where=text("status IN ('pending','paused','approved')"),
        ),
        ExcludeConstraint(
            (text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_featured_requests_window",
            using="gist",
            where=text("status = 'approved'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)

    decisions: Mapped[list["FeaturedDecision"]] = relationship(
        back_populates="request",
        order_by=lambda: (FeaturedDecision.created_at, FeaturedDecision.id),
        lazy="selectin",
    )


class FeaturedDecision(Base):
    __tablename__ = "featured_decisions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('requested','approved','rejected','revoked','paused')",
            name="ck_featured_decisions_action",
        ),
        Index("ix_featured_decisions_request_id", "request_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey("featured_requests.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)

    request: Mapped[FeaturedRequest] = relationship(back_populates="decisions")

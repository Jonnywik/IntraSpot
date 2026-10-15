from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="ck_events_status"),
        CheckConstraint(
            "registration_mode IN ('instant', 'approval')",
            name="ck_events_registration_mode",
        ),
        CheckConstraint(
            "review_window_minutes IS NULL OR review_window_minutes BETWEEN 15 AND 2880",
            name="ck_events_review_window_range",
        ),
        CheckConstraint(
            "status != 'published' OR "
            "(registration_mode = 'instant' AND review_window_minutes IS NULL) OR "
            "(registration_mode = 'approval' AND review_window_minutes IS NOT NULL "
            "AND review_window_minutes BETWEEN 15 AND 2880)",
            name="ck_events_published_review_settings",
        ),
        CheckConstraint("material_revision >= 0", name="ck_events_material_revision_nonnegative"),
        CheckConstraint("event_type = 'scheduled'", name="ck_events_event_type"),
        CheckConstraint(
            "banner_key IS NULL OR banner_key IN ('heritage', 'design', 'garden', 'music')",
            name="ck_events_banner_key",
        ),
        CheckConstraint("capacity IS NULL OR capacity > 0", name="ck_events_capacity_positive"),
        CheckConstraint("interest_count >= 0", name="ck_events_interest_count_nonnegative"),
        CheckConstraint("next_admission >= 0", name="ck_events_next_admission_nonnegative"),
        CheckConstraint(
            "status != 'published' OR published_at IS NOT NULL",
            name="ck_events_published_at",
        ),
        CheckConstraint(
            "status != 'published' OR (title IS NOT NULL AND description IS NOT NULL "
            "AND starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at "
            "AND venue_name IS NOT NULL AND venue_address IS NOT NULL "
            "AND capacity IS NOT NULL AND capacity > 0 AND banner_key IS NOT NULL)",
            name="ck_events_published_complete",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    venue_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    venue_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    banner_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost_label: Mapped[str] = mapped_column(String(100), nullable=False, default="Free", server_default="Free")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    registration_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="instant", server_default="instant")
    review_window_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    event_type: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled", server_default="scheduled")
    interest_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_admission: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    published_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)

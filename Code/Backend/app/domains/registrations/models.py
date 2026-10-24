from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class RegistrationReceipt(Base):
    __tablename__ = 'registration_receipts'
    __table_args__ = (
        UniqueConstraint('user_id', 'idempotency_key', name='uq_registration_receipts_user_key'),
        UniqueConstraint('event_id', 'event_order', name='uq_registration_receipts_event_order'),
        CheckConstraint('event_order > 0', name='ck_registration_receipts_event_order_positive'),
        CheckConstraint('http_status IS NULL OR http_status BETWEEN 100 AND 599', name='ck_registration_receipts_http_status'),
        Index('ix_registration_receipts_pending', 'event_id', 'event_order', postgresql_where=text('result IS NULL')),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    event_id: Mapped[str] = mapped_column(ForeignKey('events.id'), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    persona_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('false'))
    blocked_attendee_acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text('false'),
    )


class Registration(Base):
    __tablename__ = 'registrations'
    __table_args__ = (
        CheckConstraint(
            "status IN ('confirmed', 'waitlisted', 'pending', 'reconfirmation_required', 'cancelled', 'rejected')",
            name='ck_registrations_status',
        ),
        CheckConstraint('admission_order > 0', name='ck_registrations_admission_order_positive'),
        CheckConstraint('review_stage IS NULL OR review_stage IN (0, 1, 2)', name='ck_registrations_review_stage'),
        CheckConstraint('timeout_count >= 0', name='ck_registrations_timeout_count_nonnegative'),
        CheckConstraint('reconfirm_revision IS NULL OR reconfirm_revision > 0', name='ck_registrations_reconfirm_revision_positive'),
        Index(
            'uq_registrations_active_user_event',
            'user_id',
            'event_id',
            unique=True,
            postgresql_where=text("status IN ('confirmed', 'waitlisted', 'pending', 'reconfirmation_required')"),
        ),
        Index('ix_registrations_event_status_order', 'event_id', 'status', 'admission_order'),
        Index(
            'ix_registrations_pending_deadline', 'review_deadline', 'event_id',
            postgresql_where=text("status = 'pending' AND review_deadline IS NOT NULL"),
        ),
        Index(
            'ix_registrations_reconfirmation_deadline', 'reconfirm_deadline', 'event_id',
            postgresql_where=text("status = 'reconfirmation_required' AND reconfirm_deadline IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    event_id: Mapped[str] = mapped_column(ForeignKey('events.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    admission_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTC, default=now, onupdate=now, nullable=False)
    review_deadline: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    review_stage: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    first_reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    timeout_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text('0'))
    from_waitlist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('false'))
    persona_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('false'))
    reconfirm_deadline: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    reconfirm_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)

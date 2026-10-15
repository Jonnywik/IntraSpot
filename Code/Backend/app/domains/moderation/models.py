from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class ContentReport(Base):
    __tablename__ = 'content_reports'
    __table_args__ = (
        CheckConstraint("kind IN ('comment','message','person')", name='ck_content_reports_kind'),
        CheckConstraint(
            "reason IN ('harassment','spam','deception','impersonation','other')",
            name='ck_content_reports_reason',
        ),
        CheckConstraint(
            "status IN ('open','escalated','dismissed','removed','warned','expired')",
            name='ck_content_reports_status',
        ),
        CheckConstraint("stage IN ('organization','platform')", name='ck_content_reports_stage'),
        Index(
            'uq_content_reports_active_reporter_target',
            'reporter_id', 'kind', 'target_id',
            unique=True,
            postgresql_where=text("status IN ('open','escalated')"),
        ),
        Index('ix_content_reports_event_stage_deadline', 'event_id', 'stage', 'deadline'),
        Index(
            'ix_content_reports_subject_kind_status_deadline',
            'subject_user_id', 'kind', 'status', 'deadline',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey('events.id'), nullable=False)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    reporter_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    subject_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Deliberately opaque: reported comments and messages may be purged separately.
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)
    deadline: Mapped[datetime] = mapped_column(UTC, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)


class ReportDecision(Base):
    __tablename__ = 'report_decisions'
    __table_args__ = (
        CheckConstraint(
            "action IN ('dismiss','remove','escalate','warn','expire')",
            name='ck_report_decisions_action',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    report_id: Mapped[str] = mapped_column(ForeignKey('content_reports.id'), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)


class ContentHide(Base):
    __tablename__ = 'content_hides'
    __table_args__ = (
        CheckConstraint("kind IN ('comment','message')", name='ck_content_hides_kind'),
        UniqueConstraint('user_id', 'kind', 'target_id', name='uq_content_hides_user_target'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    event_id: Mapped[str] = mapped_column(ForeignKey('events.id'), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)

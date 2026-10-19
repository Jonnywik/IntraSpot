from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base
from app.domains.identity.models import User  # noqa: F401 - register foreign-key target
from app.domains.organizations.models import Organization  # noqa: F401 - register foreign-key target
from app.domains.announcements.models import Announcement  # noqa: F401 - register foreign-key target


class AnnouncementReport(Base):
    __tablename__ = 'announcement_reports'
    __table_args__ = (
        CheckConstraint(
            "reason IN ('harassment','spam','deception','impersonation','other')",
            name='ck_announcement_reports_reason',
        ),
        CheckConstraint(
            "status IN ('open','dismissed','hidden','restored','removed','expired')",
            name='ck_announcement_reports_status',
        ),
        CheckConstraint('reported_version > 0', name='ck_announcement_reports_version'),
        Index(
            'uq_announcement_reports_active_target',
            'reporter_id', 'announcement_id',
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index('ix_announcement_reports_org_deadline', 'org_id', 'status', 'deadline'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    announcement_id: Mapped[str] = mapped_column(ForeignKey('announcements.id'), nullable=False)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    reporter_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    subject_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reported_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)
    deadline: Mapped[datetime] = mapped_column(UTC, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)


class AnnouncementReportDecision(Base):
    __tablename__ = 'announcement_report_decisions'
    __table_args__ = (
        CheckConstraint(
            "action IN ('dismiss','hide','restore','remove','expire')",
            name='ck_announcement_report_decisions_action',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    report_id: Mapped[str] = mapped_column(ForeignKey('announcement_reports.id'), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)

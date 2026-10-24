from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base
from app.domains.events.models import Event  # noqa: F401 - register foreign-key target
from app.domains.identity.models import User  # noqa: F401 - register foreign-key target
from app.domains.organizations.models import Organization  # noqa: F401 - register foreign-key target


class EventControl(Base):
    __tablename__ = "event_controls"
    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_event_controls_version"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id"), primary_key=True
    )
    org_hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    platform_hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    removed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    cancelled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    org_reviewed_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)


class OrganizationSuspension(Base):
    __tablename__ = "organization_suspensions"
    __table_args__ = (
        CheckConstraint(
            "version >= 0", name="ck_organization_suspensions_version"
        ),
    )

    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), primary_key=True
    )
    suspended_until: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class EventReport(Base):
    __tablename__ = "event_reports"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('safety','deception')", name="ck_event_reports_reason"
        ),
        CheckConstraint(
            "stage IN ('organization','platform')", name="ck_event_reports_stage"
        ),
        CheckConstraint(
            "status IN ('open','escalated','dismissed','hidden','removed','upheld','expired')",
            name="ck_event_reports_status",
        ),
        CheckConstraint("version > 0", name="ck_event_reports_version"),
        Index(
            "uq_event_reports_active_reporter",
            "reporter_id",
            "event_id",
            unique=True,
            postgresql_where=text("status IN ('open','escalated')"),
        ),
        Index("ix_event_reports_event_created", "event_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    deadline: Mapped[datetime] = mapped_column(UTC, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)


class SafetyAudit(Base):
    __tablename__ = "safety_audits"
    __table_args__ = (
        UniqueConstraint("actor_id", "client_key", name="uq_safety_audits_actor_key"),
        CheckConstraint(
            "scope IN ('report','event','organization')", name="ck_safety_audits_scope"
        ),
        CheckConstraint(
            "action IN ('report','dismiss','hide','restore','remove','uphold','cancel','suspend','resume','expire')",
            name="ck_safety_audits_action",
        ),
        CheckConstraint("version >= 0", name="ck_safety_audits_version"),
        Index("ix_safety_audits_org_created", "org_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id"), nullable=True
    )
    report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_reports.id"), nullable=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    client_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

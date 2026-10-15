from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class MembershipApplication(Base):
    __tablename__ = 'membership_applications'
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'withdrawn', 'superseded')",
            name='ck_membership_applications_status',
        ),
        CheckConstraint(
            "reason IS NULL OR reason IN ('requirements_not_met', 'applications_closed', 'other')",
            name='ck_membership_applications_reason',
        ),
        UniqueConstraint('user_id', 'client_key', name='uq_membership_applications_user_client_key'),
        Index(
            'uq_membership_applications_pending_org_user',
            'org_id',
            'user_id',
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            'ix_membership_applications_org_status_created',
            'org_id',
            'status',
            'created_at',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    client_key: Mapped[str] = mapped_column(String(36), nullable=False)
    persona_shared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text('false')
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default='pending', server_default='pending'
    )
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)


class MembershipInvitation(Base):
    __tablename__ = 'membership_invitations'
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'revoked', 'expired', 'superseded')",
            name='ck_membership_invitations_status',
        ),
        CheckConstraint('expires_at > created_at', name='ck_membership_invitations_expiry_after_creation'),
        UniqueConstraint('sender_id', 'client_key', name='uq_membership_invitations_sender_client_key'),
        Index(
            'uq_membership_invitations_pending_org_recipient',
            'org_id',
            'recipient_id',
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index('ix_membership_invitations_status_expires', 'status', 'expires_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    recipient_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    sender_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    client_key: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default='pending', server_default='pending'
    )
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    expires_at: Mapped[datetime] = mapped_column(UTC, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)


class MembershipAudit(Base):
    __tablename__ = 'membership_audits'
    __table_args__ = (
        Index('ix_membership_audits_org_created', 'org_id', 'created_at'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    old_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)


class MembershipOperation(Base):
    __tablename__ = 'membership_operations'
    __table_args__ = (
        CheckConstraint("action IN ('leave', 'remove', 'role')", name='ck_membership_operations_action'),
        UniqueConstraint('actor_id', 'client_key', name='uq_membership_operations_actor_client_key'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    client_key: Mapped[str] = mapped_column(String(36), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)


class EventAccessRevocation(Base):
    __tablename__ = 'membership_event_revocations'
    __table_args__ = (
        CheckConstraint('cutoff_order >= 0', name='ck_membership_event_revocations_cutoff_nonnegative'),
        UniqueConstraint('event_id', 'user_id', name='uq_membership_event_revocations_event_user'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey('events.id'), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    cutoff_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now, onupdate=now)

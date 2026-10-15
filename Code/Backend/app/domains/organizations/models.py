from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class Organization(Base):
    __tablename__ = 'organizations'
    __table_args__ = (
        CheckConstraint(
            "accreditation_status IN ('pending', 'approved', 'rejected')",
            name='ck_organizations_accreditation_status',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default='')
    accreditation_status: Mapped[str] = mapped_column(String(16), nullable=False, default='pending')
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)


class OrgMembership(Base):
    __tablename__ = 'org_memberships'
    __table_args__ = (
        UniqueConstraint('org_id', 'user_id', name='uq_org_memberships_org_user'),
        CheckConstraint(
            "role IN ('owner', 'admin', 'moderator', 'member')",
            name='ck_org_memberships_role',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey('organizations.id'), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AccreditationDecision(Base):
    __tablename__ = 'accreditation_decisions'
    __table_args__ = (
        UniqueConstraint('org_id', name='uq_accreditation_decisions_org'),
        CheckConstraint(
            "outcome IN ('approved', 'rejected')",
            name='ck_accreditation_decisions_outcome',
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey('organizations.id'), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    admin_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

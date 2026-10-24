from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class OwnershipTransfer(Base):
    __tablename__ = "ownership_transfers"
    __table_args__ = (
        UniqueConstraint(
            "from_user_id",
            "client_key",
            name="uq_ownership_transfers_from_key",
        ),
        CheckConstraint(
            "status IN ('pending','accepted','declined','revoked','expired')",
            name="ck_ownership_transfers_status",
        ),
        CheckConstraint(
            "from_user_id <> nominee_id",
            name="ck_ownership_transfers_distinct_users",
        ),
        CheckConstraint("version > 0", name="ck_ownership_transfers_version"),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_ownership_transfers_expiry",
        ),
        Index(
            "uq_ownership_transfers_pending_org",
            "org_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_ownership_transfers_org_created", "org_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    from_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    nominee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    client_key: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    expires_at: Mapped[datetime] = mapped_column(UTC, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )


class OwnershipTransferAudit(Base):
    __tablename__ = "ownership_transfer_audits"
    __table_args__ = (
        CheckConstraint(
            "action IN ('requested','accepted','declined','revoked','expired')",
            name="ck_ownership_transfer_audits_action",
        ),
        Index(
            "ix_ownership_transfer_audits_transfer_created",
            "transfer_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transfer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ownership_transfers.id"), nullable=False
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

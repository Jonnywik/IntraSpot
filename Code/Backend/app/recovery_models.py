"""Retained backup references prevent object cleanup until explicit retirement."""
from datetime import datetime
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import UTC, now, uid
from app.db.session import Base


class BackupSnapshot(Base):
    __tablename__ = 'backup_snapshots'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(UTC)


class BackupObjectReference(Base):
    __tablename__ = 'backup_object_references'
    snapshot_id: Mapped[str] = mapped_column(ForeignKey('backup_snapshots.id'), primary_key=True)
    media_id: Mapped[str] = mapped_column(String(36), primary_key=True)

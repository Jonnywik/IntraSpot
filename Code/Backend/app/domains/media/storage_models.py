from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now
from app.db.session import Base


class MediaObject(Base):
    __tablename__ = 'media_objects'
    __table_args__ = (
        CheckConstraint("provider IN ('local','supabase')", name='ck_media_objects_provider'),
        CheckConstraint("status IN ('reserved','stored')", name='ck_media_objects_status'),
        CheckConstraint('byte_size > 0', name='ck_media_objects_byte_size'),
        CheckConstraint('orphan_seen_count >= 0', name='ck_media_objects_orphan_seen_count'),
        UniqueConstraint('object_key', name='uq_media_objects_object_key'),
        Index('ix_media_objects_org_status', 'org_id', 'status'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Deliberately no FK: reservation must not wait on the parent org row lock.
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    object_key: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='reserved', server_default='reserved')
    orphan_seen_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    orphan_seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    last_seen_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    backup_protected_until: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    report_protected_until: Mapped[datetime | None] = mapped_column(UTC, nullable=True)

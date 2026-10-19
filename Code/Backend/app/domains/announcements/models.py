from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base
from app.domains.identity.models import User  # noqa: F401 - register foreign-key target
from app.domains.organizations.models import Organization  # noqa: F401 - register foreign-key target


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "created_by", "client_key", name="uq_announcements_create_key"
        ),
        CheckConstraint(
            "audience IN ('public','members')", name="ck_announcements_audience"
        ),
        CheckConstraint("version > 0", name="ck_announcements_version"),
        CheckConstraint(
            "removed_at IS NOT NULL OR body IS NOT NULL", name="ck_announcements_body"
        ),
        Index("ix_announcements_org_created", "org_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    client_key: Mapped[str] = mapped_column(String(36), nullable=False)
    create_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    edited_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)


class AnnouncementRevision(Base):
    __tablename__ = "announcement_revisions"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id", "version", name="uq_announcement_revisions_version"
        ),
        CheckConstraint(
            "version > 0", name="ck_announcement_revisions_version"
        ),
        CheckConstraint(
            "audience IN ('public','members')",
            name="ck_announcement_revisions_audience",
        ),
        CheckConstraint(
            "action IN ('publish','edit','remove','hide','restore')",
            name="ck_announcement_revisions_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)


class AnnouncementReaction(Base):
    __tablename__ = "announcement_reactions"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id",
            "user_id",
            name="uq_announcement_reactions_user_post",
        ),
        CheckConstraint(
            "kind IN ('interested','excited','support','kudos','wow','relate')",
            name="ck_announcement_reactions_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

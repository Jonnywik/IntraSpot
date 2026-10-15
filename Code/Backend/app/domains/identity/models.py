from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    age_bracket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    pronouns: Mapped[str | None] = mapped_column(String(40), nullable=True)
    icebreaker: Mapped[str | None] = mapped_column(String(300), nullable=True)
    persona_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

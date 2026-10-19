from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now
from app.db.session import Base


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("language IN ('en', 'fil')", name="ck_user_preferences_language"),
        CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_user_preferences_theme"),
        CheckConstraint(
            "text_size IN ('standard', 'large', 'extra_large')",
            name="ck_user_preferences_text_size",
        ),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    language: Mapped[str] = mapped_column(String(3), nullable=False, default="en", server_default="en")
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="light", server_default="light")
    text_size: Mapped[str] = mapped_column(String(16), nullable=False, default="standard", server_default="standard")
    high_contrast: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    reduced_motion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    decoration_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    show_flash: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    updated_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

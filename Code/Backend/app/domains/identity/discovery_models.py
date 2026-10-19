from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now
from app.db.session import Base


class UserDiscoveryPreferences(Base):
    __tablename__ = "user_discovery_preferences"
    __table_args__ = (
        CheckConstraint("jsonb_typeof(availability) = 'array' AND jsonb_array_length(availability) <= 28",
                        name="ck_discovery_availability_array"),
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    coarse_area: Mapped[str | None] = mapped_column(String(80), nullable=True)
    availability: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list,
                                                    server_default=text("'[]'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

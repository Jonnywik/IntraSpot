from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("kind IN ('banner', 'logo')", name="ck_media_assets_kind"),
        CheckConstraint(
            "width > 0 AND height > 0",
            name="ck_media_assets_dimensions",
        ),
        CheckConstraint("byte_size > 0", name="ck_media_assets_byte_size"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)

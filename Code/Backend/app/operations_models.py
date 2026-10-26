"""Durable operational metadata; contains no account or request content."""
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC
from app.db.session import Base


class MaintenanceState(Base):
    __tablename__ = 'maintenance_state'
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    cursor: Mapped[str | None] = mapped_column(String(80))
    last_started_at: Mapped[object | None] = mapped_column(UTC)
    last_success_at: Mapped[object | None] = mapped_column(UTC)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    processed_count: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, server_default='0')


class RateLimitBucket(Base):
    __tablename__ = 'rate_limit_buckets'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[object] = mapped_column(UTC, nullable=False)
    expires_at: Mapped[object] = mapped_column(UTC, nullable=False, index=True)

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import UTC, now, uid
from app.db.session import Base


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    __table_args__ = (
        UniqueConstraint('event_id', 'author_id', 'client_key', name='uq_chat_messages_client_key'),
        Index('ix_chat_messages_event_sequence', 'event_id', 'sequence'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey('events.id'), nullable=False)
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, nullable=False, default=now)
    removed_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)

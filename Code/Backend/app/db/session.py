from functools import lru_cache
from threading import BoundedSemaphore

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import DomainError

# Reserve two of the hosted pool's five connections for durable media admissions.
_hosted_request_slots = BoundedSemaphore(3)


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    settings = get_settings()
    pool_size, max_overflow = (3, 2) if settings.environment == 'hosted' else (15, 5)
    return create_engine(settings.database_url, pool_pre_ping=True,
                         pool_size=pool_size, max_overflow=max_overflow)


def session_factory():
    return sessionmaker(engine(), expire_on_commit=False)


def get_db():
    hosted = get_settings().environment == 'hosted'
    acquired = not hosted or _hosted_request_slots.acquire(timeout=15)
    if not acquired:
        raise DomainError('database_busy', 'The service is busy. Please retry.', 503)
    try:
        with Session(engine(), expire_on_commit=False) as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
    finally:
        if hosted:
            _hosted_request_slots.release()

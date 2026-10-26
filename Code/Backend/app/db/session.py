from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


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
    with Session(engine(), expire_on_commit=False) as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

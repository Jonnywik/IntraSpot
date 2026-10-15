from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=15, max_overflow=5)


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

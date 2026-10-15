from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime
from app.db.session import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


UTC = DateTime(timezone=True)

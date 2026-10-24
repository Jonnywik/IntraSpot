import pytest

from app.db.models import uid
from app.domains.registrations.models import Registration


@pytest.fixture
def make_registration(db, make_user):
    def factory(event, *, status="confirmed", admission_order=1, user=None):
        user = user or make_user(nickname="Private attendee name")
        registration = Registration(
            id=uid(),
            user_id=user.id,
            event_id=event.id,
            status=status,
            admission_order=admission_order,
        )
        db.add(registration)
        db.commit()
        return registration, user

    return factory

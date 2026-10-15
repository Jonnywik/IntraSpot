from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import now
from app.domains.events.models import Event
from app.domains.registrations.models import Registration, RegistrationReceipt


def auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.parametrize(
    ('user_fields', 'error_code'),
    [
        pytest.param({'email': 'fictional@example.test'}, 'registration_ineligible', id='non-plm-email'),
        pytest.param(
            {'email_verified': False}, 'registration_ineligible', id='unverified-plm-email'
        ),
        pytest.param({'nickname': None}, 'profile_incomplete', id='missing-nickname'),
        pytest.param({'age_bracket': None}, 'profile_incomplete', id='missing-age-bracket'),
        pytest.param({'tags': []}, 'profile_incomplete', id='missing-interest'),
    ],
)
def test_registration_enforces_eligibility_and_each_required_profile_field(
    client, db, make_event, make_user, token_for, user_fields, error_code
):
    event = make_event()
    user = make_user(**user_fields)

    response = client.post(
        f'/api/v1/events/{event.id}/registrations',
        headers=auth(token_for(user)) | {'Idempotency-Key': 'sprint4-gate-key-01'},
    )

    assert response.status_code == 403
    assert response.json()['error']['code'] == error_code
    assert 'request_id' in response.json()
    db.expire_all()
    assert db.scalar(
        select(func.count(Registration.id)).where(
            Registration.user_id == user.id,
            Registration.event_id == event.id,
        )
    ) == 0


def test_registration_rejects_reuse_of_key_for_another_event_at_http_boundary(
    client, db, make_event, make_user, token_for
):
    event = make_event()
    other_event = make_event()
    user = make_user()
    headers = auth(token_for(user))
    key = 'cross-event-key-001'

    first = client.post(
        f'/api/v1/events/{event.id}/registrations',
        headers=headers | {'Idempotency-Key': key},
    )
    conflict = client.post(
        f'/api/v1/events/{other_event.id}/registrations',
        headers=headers | {'Idempotency-Key': key},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'idempotency_key_reused'
    db.expire_all()
    assert db.scalar(
        select(func.count(Registration.id)).where(Registration.user_id == user.id)
    ) == 1
    assert db.scalar(
        select(Event.next_admission).where(Event.id == other_event.id)
    ) == 0


def test_active_registration_with_a_different_key_returns_the_same_http_result(
    client, db, make_event, make_user, token_for
):
    event = make_event(capacity=1)
    user = make_user()
    headers = auth(token_for(user))

    first = client.post(
        f'/api/v1/events/{event.id}/registrations',
        headers=headers | {'Idempotency-Key': 'active-key-one'},
    )
    duplicate = client.post(
        f'/api/v1/events/{event.id}/registrations',
        headers=headers | {'Idempotency-Key': 'active-key-two'},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()
    db.expire_all()
    assert db.scalar(
        select(func.count(Registration.id)).where(
            Registration.user_id == user.id,
            Registration.event_id == event.id,
        )
    ) == 1
    assert db.scalar(
        select(func.count(RegistrationReceipt.id)).where(
            RegistrationReceipt.user_id == user.id,
            RegistrationReceipt.event_id == event.id,
        )
    ) == 2


def test_my_registrations_mark_past_events_and_isolate_each_caller(
    client, db, make_event, make_user, token_for
):
    first_user, other_user = make_user(), make_user()
    first_event = make_event(title='First historical event')
    other_event = make_event(title='Other historical event')

    first_registration = client.post(
        f'/api/v1/events/{first_event.id}/registrations',
        headers=auth(token_for(first_user)) | {'Idempotency-Key': 'past-first-key-01'},
    )
    other_registration = client.post(
        f'/api/v1/events/{other_event.id}/registrations',
        headers=auth(token_for(other_user)) | {'Idempotency-Key': 'past-other-key-01'},
    )
    assert first_registration.status_code == other_registration.status_code == 201

    past_start = now() - timedelta(days=1)
    for event in (first_event, other_event):
        event.starts_at = past_start
        event.ends_at = past_start + timedelta(hours=1)
    db.commit()

    first_list = client.get(
        '/api/v1/me/registrations', headers=auth(token_for(first_user))
    )
    other_list = client.get(
        '/api/v1/me/registrations', headers=auth(token_for(other_user))
    )

    assert first_list.status_code == other_list.status_code == 200
    assert len(first_list.json()) == len(other_list.json()) == 1
    first_row, other_row = first_list.json()[0], other_list.json()[0]
    assert first_row['id'] == first_registration.json()['id']
    assert first_row['event_id'] == first_event.id
    assert first_row['is_past'] is True
    assert first_row['event_title'] == 'First historical event'
    assert other_row['id'] == other_registration.json()['id']
    assert other_row['event_id'] == other_event.id
    assert other_row['is_past'] is True
    assert other_row['event_title'] == 'Other historical event'

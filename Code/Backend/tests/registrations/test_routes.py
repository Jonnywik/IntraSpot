from uuid import uuid4

from app.domains.registrations import service


def test_my_events_is_self_only_and_returns_current_waitlist_position(client, make_event, make_user, token_for):
    event = make_event(capacity=1)
    other = make_user(nickname='PRIVATE OTHER PERSONA')
    attendee = make_user(nickname='FICTIONAL SELF PERSONA')
    service.submit_registration(other.id, event.id, 'other-key-0001')

    headers = {
        'Authorization': f'Bearer {token_for(attendee)}',
        'Idempotency-Key': 'attendee-key-01',
    }
    created = client.post(f'/api/v1/events/{event.id}/registrations', headers=headers)
    assert created.status_code == 201
    assert created.json()['status'] == 'waitlisted'
    assert created.json()['waitlist_position'] == 1
    assert created.json()['waitlist_message'] == 'You are on the waitlist. No estimated wait time is available.'
    assert set(created.json()) == {
        'id', 'event_id', 'status', 'waitlist_position', 'waitlist_message', 'admission_order',
        'review_deadline', 'review_stage', 'reviewer_id', 'first_reviewer_id',
        'timeout_count', 'from_waitlist', 'persona_shared', 'reconfirm_deadline',
        'reconfirm_revision',
    }
    assert created.json()['persona_shared'] is False

    response = client.get('/api/v1/me/registrations', headers={'Authorization': headers['Authorization']})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]['id'] == created.json()['id']
    assert body[0]['waitlist_position'] == 1
    assert body[0]['waitlist_message'] == 'You are on the waitlist. No estimated wait time is available.'
    assert other.id not in response.text
    assert other.email not in response.text
    assert other.nickname not in response.text


def test_malformed_event_id_maps_to_stable_422_without_identity_leak(client, make_event, make_user, token_for):
    event = make_event()
    actor = make_user(nickname='FICTIONAL SELF PERSONA')
    headers = {'Authorization': f'Bearer {token_for(actor)}', 'Idempotency-Key': 'contract-key-01'}
    malformed = 'malformed-event-id-DO-NOT-ECHO'

    register = client.post(f'/api/v1/events/{malformed}/registrations', headers=headers)
    withdraw = client.delete(f'/api/v1/events/{malformed}/registrations/me', headers={'Authorization': headers['Authorization']})

    assert register.status_code == 422
    assert register.json()['error']['code'] == 'validation_error'
    assert 'request_id' in register.json()
    assert withdraw.status_code == 422
    assert withdraw.json()['error']['code'] == 'validation_error'
    assert 'request_id' in withdraw.json()
    for response in (register, withdraw):
        assert malformed not in response.text
        assert event.id not in response.text
        assert actor.nickname not in response.text


def test_missing_or_malformed_idempotency_key_maps_to_stable_422(client, make_event, make_user, token_for):
    event = make_event()
    actor = make_user()
    auth = {'Authorization': f'Bearer {token_for(actor)}'}

    missing = client.post(f'/api/v1/events/{event.id}/registrations', headers=auth)
    short = client.post(
        f'/api/v1/events/{event.id}/registrations',
        headers=auth | {'Idempotency-Key': 'short'},
    )

    assert missing.status_code == 422
    assert missing.json()['error']['code'] == 'validation_error'
    assert 'request_id' in missing.json()
    assert short.status_code == 422
    assert short.json()['error']['code'] == 'validation_error'
    assert 'request_id' in short.json()
    assert 'short' not in short.text


def test_withdraw_is_idempotent_and_returns_current_state(client, make_event, make_user, token_for):
    event = make_event(capacity=1)
    holder = make_user()
    service.submit_registration(holder.id, event.id, 'withdraw-holder-01')
    attendee = make_user()
    created = client.post(
        f'/api/v1/events/{event.id}/registrations',
        headers={'Authorization': f'Bearer {token_for(attendee)}', 'Idempotency-Key': 'withdraw-user-01'},
    )
    assert created.status_code == 201
    auth = {'Authorization': f'Bearer {token_for(attendee)}'}

    first = client.delete(f'/api/v1/events/{event.id}/registrations/me', headers=auth)
    second = client.delete(f'/api/v1/events/{event.id}/registrations/me', headers=auth)
    unknown = client.delete(f'/api/v1/events/{uuid4()}/registrations/me', headers=auth)

    assert first.status_code == 200
    assert first.json()['status'] == 'cancelled'
    assert second.status_code == 200
    assert second.json() == first.json()
    assert unknown.status_code == 404
    assert unknown.json()['error']['code'] == 'event_not_found'
    mine = client.get('/api/v1/me/registrations', headers=auth)
    assert mine.json()[0]['status'] == 'cancelled'

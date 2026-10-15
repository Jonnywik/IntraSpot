from datetime import timedelta

from app.db.models import now


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_four_core_journeys(client, make_user, token_for):
    owner = make_user(nickname='Fictional owner')
    admin = make_user(platform_admin=True, nickname='Fictional platform admin')
    student = make_user(nickname='Fictional student')
    faculty = make_user(email='fictional-faculty@faculty.plm.edu.ph', nickname='Fictional faculty')
    owner_headers, admin_headers = auth(token_for(owner)), auth(token_for(admin))
    org_response = client.post('/api/v1/organizations', json={'name': 'Fictional Journey Club'}, headers=owner_headers)
    assert org_response.status_code in {200, 201}, org_response.text
    org = org_response.json()
    assert org['accreditation_status'] == 'pending'
    start = now() + timedelta(days=3)
    event_response = client.post(f"/api/v1/organizations/{org['id']}/events", headers=owner_headers, json={
        'title': 'Fictional Journey Event', 'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=2)).isoformat(),
        'venue_name': 'Fictional courtyard', 'venue_address': 'Intramuros, Manila', 'description': 'Local-only test event',
        'capacity': 1, 'banner_key': 'heritage', 'cost_label': 'Free',
    })
    assert event_response.status_code in {200, 201}, event_response.text
    event_id = event_response.json()['id']
    assert client.get(f'/api/v1/events/{event_id}').status_code == 404
    assert client.post(f'/api/v1/events/{event_id}/publish', headers=owner_headers).status_code in {403, 409}
    decision = client.post(f"/api/v1/platform-admin/organizations/{org['id']}/accreditation-decision",
                           headers=admin_headers, json={'outcome': 'approved'})
    assert decision.status_code in {200, 201}, decision.text
    workspace = client.get(f"/api/v1/organizations/{org['id']}/workspace", headers=owner_headers).json()
    assert workspace['accreditation_status'] == 'approved'
    assert workspace['decisions'][0]['admin_id'] == admin.id
    assert workspace['decisions'][0]['decided_at']
    assert client.post(f'/api/v1/events/{event_id}/publish', headers=owner_headers).status_code == 200
    events = client.get('/api/v1/events', params={'q': 'Journey Club'}).json()
    assert any(row['id'] == event_id for row in events)
    assert client.get('/api/v1/events', params={'q': 'Fictional courtyard'}).json() == []
    detail = client.get(f'/api/v1/events/{event_id}').json()
    assert detail['confirmed_count'] == 0 and detail['remaining_spots'] == 1
    result = client.post(f'/api/v1/events/{event_id}/registrations', headers=auth(token_for(student)) | {'Idempotency-Key': 'student-journey-1'})
    assert result.status_code in {200, 201}, result.text
    assert result.json()['status'] == 'confirmed'
    queued = client.post(f'/api/v1/events/{event_id}/registrations', headers=auth(token_for(faculty)) | {'Idempotency-Key': 'faculty-journey-1'})
    assert queued.status_code in {200, 201}, queued.text
    original = queued.json()
    assert original['status'] == 'waitlisted' and original['waitlist_position'] == 1
    assert 'no estimated wait time' in original['waitlist_message'].lower()
    mine = client.get('/api/v1/me/registrations', headers=auth(token_for(faculty))).json()
    assert len(mine) == 1 and mine[0]['status'] == 'waitlisted'
    assert client.delete(f'/api/v1/events/{event_id}/registrations/me', headers=auth(token_for(student))).status_code == 200
    promoted = client.get('/api/v1/me/registrations', headers=auth(token_for(faculty))).json()
    assert promoted[0]['status'] == 'confirmed'
    retried = client.post(f'/api/v1/events/{event_id}/registrations', headers=auth(token_for(faculty)) | {'Idempotency-Key': 'faculty-journey-1'})
    assert retried.json() == original
    notices = client.get('/api/v1/me/notifications', headers=auth(token_for(faculty))).json()
    assert len(notices) == 1 and notices[0]['kind'] == 'waitlist_promoted'
    assert client.get('/api/v1/me/notifications', headers=auth(token_for(student))).json() == []
    assert client.patch(f'/api/v1/events/{event_id}/draft', headers=owner_headers, json={'capacity': 5}).status_code in {403, 409}


def test_incomplete_and_non_plm_registration_deny_without_seat(client, make_event, make_user, token_for):
    event = make_event()
    incomplete = make_user(nickname=None, age_bracket=None, tags=[])
    external = make_user(email='fictional@evilplm.edu.ph')
    for user in (incomplete, external):
        response = client.post(f'/api/v1/events/{event.id}/registrations', headers=auth(token_for(user)) | {'Idempotency-Key': f'blocked-{user.id}'})
        assert response.status_code in {400, 403, 409, 422}
        assert 'email' not in response.text and 'fictional@' not in response.text
    detail = client.get(f'/api/v1/events/{event.id}').json()
    assert detail['confirmed_count'] == 0 and detail['remaining_spots'] == 3

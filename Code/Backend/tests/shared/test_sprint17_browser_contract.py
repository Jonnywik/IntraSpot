"""Real browsers must be allowed to send the authenticated planning PUT."""
from app.db.models import uid


def test_saved_event_put_preflight_preserves_the_explicit_origin_allowlist(client):
    path = '/api/v1/me/saved-events/' + uid()
    headers = {'Origin': 'http://127.0.0.1:3000',
               'Access-Control-Request-Method': 'PUT',
               'Access-Control-Request-Headers': 'Authorization'}
    allowed = client.options(path, headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers['Access-Control-Allow-Origin'] == headers['Origin']
    assert 'PUT' in allowed.headers['Access-Control-Allow-Methods']
    forbidden = client.options(path, headers=headers | {'Origin': 'https://untrusted.example'})
    assert forbidden.status_code == 400
    assert 'Access-Control-Allow-Origin' not in forbidden.headers
    assert client.put(path, headers={'Origin': headers['Origin']}).status_code == 401

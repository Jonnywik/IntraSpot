"""Draft autosave conflicts are checked inside the existing PostgreSQL lock."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def setup_draft(make_user, make_org, make_event, token_for, **org_fields):
    owner = make_user()
    org = make_org(owner=owner, **org_fields)
    event = make_event(org=org, status="draft", published_at=None)
    headers = {"Authorization": f"Bearer {token_for(owner)}"}
    return event, headers


def test_conditional_save_rejects_stale_edits_without_losing_saved_content(
    client, db, make_user, make_org, make_event, token_for,
):
    event, headers = setup_draft(make_user, make_org, make_event, token_for)
    path = f"/api/v1/events/{event.id}/draft"
    initial = client.get(path, headers=headers).json()
    guarded = headers | {"If-Match": f'"{initial["draft_version"]}"'}
    saved = client.patch(path, headers=guarded, json={"title": "First window"})
    assert saved.status_code == 200
    assert saved.json()["draft_version"] != initial["draft_version"]
    stale = client.patch(path, headers=guarded, json={"title": "Stale window"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "draft_conflict"
    current = client.get(path, headers=headers).json()
    assert current["title"] == "First window"
    assert current["draft_version"] == saved.json()["draft_version"]
    db.refresh(event)
    assert event.title == "First window"


def test_version_is_stable_for_equivalent_content_and_timezone(
    client, make_user, make_org, make_event, token_for,
):
    event, headers = setup_draft(make_user, make_org, make_event, token_for)
    path = f"/api/v1/events/{event.id}/draft"
    initial = client.get(path, headers=headers).json()
    result = client.patch(path, headers=headers | {"If-Match": f'"{initial["draft_version"]}"'},
                          json={"starts_at": event.starts_at.astimezone(timezone(timedelta(hours=8))).isoformat()})
    assert result.status_code == 200
    assert result.json()["draft_version"] == initial["draft_version"]
    assert client.get(path, headers=headers).json()["draft_version"] == initial["draft_version"]


def test_stale_preview_cannot_publish_and_public_result_has_no_draft_version(
    client, make_user, make_org, make_event, token_for,
):
    event, headers = setup_draft(make_user, make_org, make_event, token_for)
    path = f"/api/v1/events/{event.id}"
    initial = client.get(path + "/draft", headers=headers).json()
    saved = client.patch(path + "/draft", headers=headers,
                         json={"title": "Updated before publish"}).json()
    stale = client.post(path + "/publish", headers=headers | {"If-Match": f'"{initial["draft_version"]}"'})
    assert stale.status_code == 409
    assert client.get(path).status_code == 404
    result = client.post(path + "/publish", headers=headers | {"If-Match": f'"{saved["draft_version"]}"'})
    assert result.status_code == 200
    assert result.json()["title"] == "Updated before publish"
    assert "draft_version" not in result.json()
    assert "draft_version" not in client.get(path).json()


def test_guarded_concurrent_saves_have_one_winner(
    client, make_user, make_org, make_event, token_for,
):
    event, headers = setup_draft(make_user, make_org, make_event, token_for)
    path = f"/api/v1/events/{event.id}/draft"
    version = client.get(path, headers=headers).json()["draft_version"]
    guarded = headers | {"If-Match": f'"{version}"'}

    def save(title):
        with TestClient(create_app()) as contender:
            return contender.patch(path, headers=guarded, json={"title": title})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["Window A", "Window B"]))
    assert sorted(response.status_code for response in results) == [200, 409]
    winner = next(response.json() for response in results if response.status_code == 200)
    current = client.get(path, headers=headers).json()
    assert (current["title"], current["draft_version"]) == (winner["title"], winner["draft_version"])


def test_preconditions_do_not_bypass_authorization_or_pending_publish_gate(
    client, make_user, make_org, make_event, token_for,
):
    event, headers = setup_draft(make_user, make_org, make_event, token_for,
                                 accreditation_status="pending")
    path = f"/api/v1/events/{event.id}"
    version = client.get(path + "/draft", headers=headers).json()["draft_version"]
    guarded = headers | {"If-Match": f'"{version}"'}
    assert client.post(path + "/publish", headers=guarded).status_code == 403
    outsider = {"Authorization": f"Bearer {token_for(make_user())}", "If-Match": f'"{version}"'}
    assert client.patch(path + "/draft", headers=outsider, json={"title": "Denied"}).status_code == 403
    assert client.get(path + "/draft", headers=headers).json()["draft_version"] == version


def test_conditional_save_header_is_allowed_for_local_frontend(client):
    response = client.options("/api/v1/events/00000000-0000-0000-0000-000000000000/draft", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "authorization,content-type,if-match",
    })
    assert response.status_code == 200
    assert "if-match" in response.headers["access-control-allow-headers"].lower()

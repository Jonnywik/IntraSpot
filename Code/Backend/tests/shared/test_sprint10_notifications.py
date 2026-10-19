from app.notifications import Notification, notify_in_app


def test_notification_context_is_derived_for_new_and_legacy_rows_without_writing_on_read(
    client, db, make_user, make_event, token_for,
):
    user = make_user()
    other = make_user()
    event = make_event()
    notify_in_app(db, user_id=user.id, event_id=event.id, kind="registration_review_requested",
                  message="A registration is waiting for your event review.", dedupe_key="new-context")
    legacy = Notification(user_id=user.id, event_id=event.id, org_id=None,
                          kind="waitlist_promoted", message="A spot opened.", dedupe_key="legacy-context")
    db.add(legacy)
    db.commit()
    headers = {"Authorization": f"Bearer {token_for(user)}"}
    response = client.get("/api/v1/me/notifications", headers=headers)
    assert response.status_code == 200 and len(response.json()) == 2
    assert all(item["org_id"] == event.org_id for item in response.json())
    assert all("user_id" not in item and "dedupe_key" not in item for item in response.json())
    db.refresh(legacy)
    assert legacy.org_id is None
    result = client.post(f"/api/v1/me/notifications/{legacy.id}/read", headers=headers)
    assert result.status_code == 200 and result.json()["org_id"] == event.org_id
    outsider = {"Authorization": f"Bearer {token_for(other)}"}
    assert client.get("/api/v1/me/notifications", headers=outsider).json() == []
    assert client.post(f"/api/v1/me/notifications/{legacy.id}/read", headers=outsider).status_code == 404

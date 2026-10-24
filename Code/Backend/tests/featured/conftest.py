from datetime import datetime, timezone

from sqlalchemy import text


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def request_featured(client, event_id, user, token_for):
    return client.post(
        f"/api/v1/events/{event_id}/featured-requests",
        headers=auth(token_for(user)),
    )


def owned_event(make_event, make_org, owner, **fields):
    return make_event(org=make_org(owner=owner), **fields)


def decide_featured(
    client,
    request_id,
    admin,
    token_for,
    action,
    version,
    *,
    starts_at="omit",
    ends_at="omit",
    extra=None,
):
    body = {"action": action, "version": version}
    if starts_at != "omit":
        body["starts_at"] = iso(starts_at) if isinstance(starts_at, datetime) else starts_at
    if ends_at != "omit":
        body["ends_at"] = iso(ends_at) if isinstance(ends_at, datetime) else ends_at
    if extra:
        body.update(extra)
    return client.post(
        f"/api/v1/platform-admin/featured-requests/{request_id}/decisions",
        headers=auth(token_for(admin)),
        json=body,
    )


def rows_for_event(db, event_id):
    db.expire_all()
    return list(
        db.execute(
            text("SELECT * FROM featured_requests WHERE event_id = :event_id ORDER BY requested_at, id"),
            {"event_id": event_id},
        ).mappings()
    )


def decisions_for_request(db, request_id):
    db.expire_all()
    return list(
        db.execute(
            text("SELECT * FROM featured_decisions WHERE request_id = :request_id ORDER BY created_at, id"),
            {"request_id": request_id},
        ).mappings()
    )

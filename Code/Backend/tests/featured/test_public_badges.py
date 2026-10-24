from datetime import timedelta

from sqlalchemy import event as sqlalchemy_event

from app.db.models import now, uid
from app.db.session import engine
from app.domains.organizations.models import OrgMembership
from app.domains.registrations import service as registration_service

from .conftest import auth, decide_featured, request_featured


def read_with_feature_query_count(call):
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        if "featured_requests" in statement.lower():
            statements.append(statement)

    database_engine = engine()
    sqlalchemy_event.listen(database_engine, "before_cursor_execute", capture)
    try:
        response = call()
    finally:
        sqlalchemy_event.remove(database_engine, "before_cursor_execute", capture)
    return response, len(statements)


def test_featured_badges_use_batch_reads_without_changing_feed_behavior_or_leaking_audit(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    other_owner = make_user()
    reader = make_user()
    admin = make_user(platform_admin=True)
    organization = make_org(owner=owner, name="Target Arts Club")
    other_organization = make_org(owner=other_owner, name="Target Garden Club")
    db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=reader.id, role="member", active=True))
    db.commit()

    base = now() + timedelta(days=1)
    outside = make_event(
        org=other_organization,
        title="Target outside club",
        starts_at=base,
        ends_at=base + timedelta(hours=2),
        published_at=now() - timedelta(days=1),
    )
    earliest = make_event(
        org=organization,
        title="Target early club event",
        starts_at=base + timedelta(days=1),
        ends_at=base + timedelta(days=1, hours=2),
        published_at=now() - timedelta(days=3),
    )
    featured = make_event(
        org=organization,
        title="Target featured club event",
        starts_at=base + timedelta(days=2),
        ends_at=base + timedelta(days=2, hours=2),
        published_at=now() - timedelta(days=2),
    )

    requested = request_featured(client, featured.id, owner, token_for)
    approved = decide_featured(
        client,
        requested.json()["id"],
        admin,
        token_for,
        "approve",
        1,
        ends_at=now() + timedelta(hours=1),
    )
    assert approved.status_code == 200
    request_id = approved.json()["id"]
    decision_ids = [decision["id"] for decision in approved.json()["decisions"]]

    registration = registration_service.submit_registration(
        reader.id, featured.id, "featured-badge-my-event-01"
    )
    assert registration.http_status == 201
    reader_headers = auth(token_for(reader))
    for event in (outside, earliest, featured):
        saved = client.put(f"/api/v1/me/saved-events/{event.id}", headers=reader_headers)
        assert saved.status_code == 200

    upcoming, upcoming_feature_queries = read_with_feature_query_count(
        lambda: client.get("/api/v1/events?sort=upcoming")
    )
    paginated, pagination_feature_queries = read_with_feature_query_count(
        lambda: client.get("/api/v1/events?sort=upcoming&limit=1&offset=1")
    )
    newest, newest_feature_queries = read_with_feature_query_count(
        lambda: client.get("/api/v1/events?sort=newest")
    )
    searched, search_feature_queries = read_with_feature_query_count(
        lambda: client.get("/api/v1/events?q=Target")
    )
    my_clubs, clubs_feature_queries = read_with_feature_query_count(
        lambda: client.get("/api/v1/events?my_clubs=true", headers=reader_headers)
    )
    saved_events, saved_feature_queries = read_with_feature_query_count(
        lambda: client.get("/api/v1/me/saved-events", headers=reader_headers)
    )
    my_events, my_events_feature_queries = read_with_feature_query_count(
        lambda: client.get("/api/v1/me/registrations", headers=reader_headers)
    )
    public_detail = client.get(f"/api/v1/events/{featured.id}")

    assert all(
        response.status_code == 200
        for response in (
            upcoming,
            paginated,
            newest,
            searched,
            my_clubs,
            saved_events,
            my_events,
            public_detail,
        )
    )
    assert [item["id"] for item in upcoming.json()] == [outside.id, earliest.id, featured.id]
    assert [item["id"] for item in paginated.json()] == [earliest.id]
    assert [item["id"] for item in newest.json()] == [outside.id, featured.id, earliest.id]
    assert [item["id"] for item in searched.json()] == [outside.id, earliest.id, featured.id]
    assert [item["id"] for item in my_clubs.json()] == [earliest.id, featured.id]
    assert upcoming.json()[-1]["is_featured"] is True
    assert newest.json()[1]["is_featured"] is True
    assert searched.json()[-1]["is_featured"] is True
    assert my_clubs.json()[-1]["is_featured"] is True
    saved_by_id = {item["event_id"]: item["event"] for item in saved_events.json()}
    assert saved_by_id[featured.id]["is_featured"] is True
    assert saved_by_id[earliest.id]["is_featured"] is False
    assert len(my_events.json()) == 1
    assert my_events.json()[0]["event_id"] == featured.id
    assert my_events.json()[0]["is_featured"] is True
    assert public_detail.json()["is_featured"] is True
    assert {
        upcoming_feature_queries,
        pagination_feature_queries,
        newest_feature_queries,
        search_feature_queries,
        clubs_feature_queries,
        saved_feature_queries,
        my_events_feature_queries,
    } == {1}

    public_payloads = [
        upcoming.json(),
        paginated.json(),
        newest.json(),
        searched.json(),
        my_clubs.json(),
        saved_events.json(),
        my_events.json(),
        public_detail.json(),
    ]
    public_text = str(public_payloads)
    assert request_id not in public_text
    assert all(decision_id not in public_text for decision_id in decision_ids)
    assert all(
        "decisions" not in item and "snapshot_hash" not in item
        for response in (upcoming, newest, searched, my_clubs, my_events)
        for item in response.json()
    )

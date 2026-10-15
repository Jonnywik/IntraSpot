from datetime import timedelta

from app.db.models import now, uid
from app.domains.organizations.models import OrgMembership


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_public_search_does_not_match_venue_name_or_address(client, make_event):
    make_event(venue_name="PrivateGardenHall", venue_address="9 Orchid Lane")

    for query in ("PrivateGardenHall", "Orchid Lane"):
        response = client.get("/api/v1/events", params={"q": query})
        assert response.status_code == 200
        assert response.json() == []


def test_my_clubs_returns_empty_for_eligible_users_without_active_memberships(
    client, db, make_user, make_org, make_event, token_for
):
    no_memberships = make_user()
    inactive_only = make_user()
    owner = make_user()
    organization = make_org(owner=owner)
    db.add(
        OrgMembership(
            id=uid(),
            org_id=organization.id,
            user_id=inactive_only.id,
            role="member",
            active=False,
        )
    )
    db.commit()
    make_event(org=organization, title="Studio gathering")

    for user in (no_memberships, inactive_only):
        response = client.get(
            "/api/v1/events",
            params={"my_clubs": "true"},
            headers=auth(token_for(user)),
        )
        assert response.status_code == 200
        assert response.json() == []


def test_search_and_my_clubs_compose_with_upcoming_and_newest_tie_breaks(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    member = make_user()
    club = make_org(owner=owner, name="Fictional Arts Club")
    inactive_club = make_org(name="Fictional Inactive Club")
    outside_club = make_org(name="Fictional Outside Club")
    db.add_all(
        [
            OrgMembership(
                id=uid(), org_id=club.id, user_id=member.id, role="member", active=True
            ),
            OrgMembership(
                id=uid(),
                org_id=inactive_club.id,
                user_id=member.id,
                role="member",
                active=False,
            ),
        ]
    )
    db.commit()

    base = now()
    earliest = make_event(
        org=club,
        id="00000000-0000-0000-0000-000000000003",
        title="Studio earliest",
        starts_at=base + timedelta(days=1),
        ends_at=base + timedelta(days=1, hours=2),
        published_at=base - timedelta(days=3),
    )
    tied_first = make_event(
        org=club,
        id="00000000-0000-0000-0000-000000000001",
        title="Studio tie first",
        starts_at=base + timedelta(days=2),
        ends_at=base + timedelta(days=2, hours=2),
        published_at=base - timedelta(days=2),
    )
    tied_second = make_event(
        org=club,
        id="00000000-0000-0000-0000-000000000002",
        title="Studio tie second",
        starts_at=base + timedelta(days=2),
        ends_at=base + timedelta(days=2, hours=2),
        published_at=base - timedelta(days=2),
    )
    newest = make_event(
        org=club,
        id="00000000-0000-0000-0000-000000000004",
        title="Studio newest",
        starts_at=base + timedelta(days=3),
        ends_at=base + timedelta(days=3, hours=2),
        published_at=base - timedelta(days=1),
    )
    make_event(org=club, title="Garden gathering")
    make_event(org=inactive_club, title="Studio inactive club")
    make_event(org=outside_club, title="Studio outside club")

    headers = auth(token_for(member))
    params = {"my_clubs": "true", "q": "Studio"}
    upcoming_ids = [earliest.id, tied_first.id, tied_second.id, newest.id]
    default_sort = client.get("/api/v1/events", params=params, headers=headers)
    assert default_sort.status_code == 200
    assert [event["id"] for event in default_sort.json()] == upcoming_ids

    newest_sort = client.get(
        "/api/v1/events", params={**params, "sort": "newest"}, headers=headers
    )
    assert newest_sort.status_code == 200
    assert [event["id"] for event in newest_sort.json()] == [
        newest.id,
        tied_first.id,
        tied_second.id,
        earliest.id,
    ]

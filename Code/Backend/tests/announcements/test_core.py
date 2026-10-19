from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.contracts import Actor
from app.db.models import now, uid
from app.domains.announcements.models import Announcement, AnnouncementReaction, AnnouncementRevision
from app.domains.moderation.models import ContentReport
from app.domains.organizations.models import OrgMembership


def auth(user, token_for):
    return {"Authorization": f"Bearer {token_for(user)}"}


def actor_for(user, *, eligible=True):
    return Actor(
        user_id=user.id,
        nickname=user.nickname,
        eligible=eligible,
        profile_complete=True,
        platform_admin=user.platform_admin,
    )


def announcement_payload(title="A campus update", *, audience="public", key=None, body="A fictional update."):
    return {
        "title": title,
        "body": body,
        "audience": audience,
        "client_key": str(key or uuid4()),
    }


def add_membership(db, organization, user, *, role="member", active=True):
    membership = OrgMembership(
        id=uid(), org_id=organization.id, user_id=user.id, role=role, active=active
    )
    db.add(membership)
    db.commit()
    return membership


def seed_announcement(
    db,
    organization,
    owner,
    title,
    *,
    audience="public",
    created_at=None,
    hidden=False,
    removed=False,
):
    timestamp = created_at or now()
    original_body = f"Evidence for {title}."
    version = 2 if removed else 1
    post = Announcement(
        id=uid(),
        org_id=organization.id,
        created_by=owner.id,
        title=title,
        body=None if removed else original_body,
        audience=audience,
        version=version,
        client_key=str(uuid4()),
        create_hash=sha256(f"{title}:{original_body}:{audience}".encode()).hexdigest(),
        created_at=timestamp,
        updated_at=timestamp,
        hidden_at=timestamp if hidden else None,
        removed_at=timestamp if removed else None,
    )
    db.add(post)
    db.flush()
    for revision_version in range(1, version + 1):
        final_removed_revision = removed and revision_version == version
        db.add(
            AnnouncementRevision(
                id=uid(),
                announcement_id=post.id,
                version=revision_version,
                actor_id=owner.id,
                action="remove" if final_removed_revision else "publish" if revision_version == 1 else "edit",
                title=title,
                body=None if final_removed_revision else original_body,
                audience=audience,
                created_at=timestamp + timedelta(seconds=revision_version),
            )
        )
    db.commit()
    return post


def test_visibility_is_filtered_before_paging_and_managers_use_manage_history_routes(
    client, db, make_user, make_org, token_for
):
    owner = make_user(nickname="Private fictional author")
    organization = make_org(owner=owner)
    member = make_user()
    add_membership(db, organization, member, role="moderator")

    base = now() - timedelta(minutes=1)
    removed = seed_announcement(
        db, organization, owner, "Removed newest", created_at=base + timedelta(seconds=4), removed=True
    )
    hidden = seed_announcement(
        db, organization, owner, "Hidden next", created_at=base + timedelta(seconds=3), hidden=True
    )
    members_only = seed_announcement(
        db,
        organization,
        owner,
        "Members newest",
        audience="members",
        created_at=base + timedelta(seconds=2),
    )
    public_newest = seed_announcement(
        db, organization, owner, "Public newest", created_at=base + timedelta(seconds=1)
    )
    public_older = seed_announcement(db, organization, owner, "Public older", created_at=base)

    collection_url = f"/api/v1/organizations/{organization.id}/announcements"
    guest_page = client.get(collection_url, params={"limit": 2})
    member_page = client.get(
        collection_url, params={"limit": 2}, headers=auth(member, token_for)
    )

    assert guest_page.status_code == member_page.status_code == 200
    assert [item["title"] for item in guest_page.json()] == ["Public newest", "Public older"]
    assert [item["title"] for item in member_page.json()] == ["Members newest", "Public newest"]
    assert all("created_by" not in item and "author_id" not in item for item in guest_page.json())
    assert owner.email not in guest_page.text
    assert owner.nickname not in guest_page.text
    assert set(guest_page.json()[0]) == {
        "id",
        "org_id",
        "organization_name",
        "title",
        "body",
        "audience",
        "version",
        "created_at",
        "updated_at",
        "edited_at",
        "state",
    }

    owner_headers = auth(owner, token_for)
    for post in (hidden, removed):
        assert client.get(f"/api/v1/announcements/{post.id}", headers=owner_headers).status_code == 404
        history = client.get(f"/api/v1/announcements/{post.id}/history", headers=owner_headers)
        assert history.status_code == 200
        assert history.json()

    managed = client.get(
        f"/api/v1/organizations/{organization.id}/announcements/manage", headers=owner_headers
    )
    assert managed.status_code == 200
    states = {item["id"]: item["state"] for item in managed.json()}
    assert states[hidden.id] == "hidden"
    assert states[removed.id] == "removed"
    assert members_only.id not in {item["id"] for item in guest_page.json()}
    assert public_older.id != public_newest.id


def test_only_approved_eligible_owner_or_admin_members_can_author(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    admin = make_user()
    moderator = make_user()
    member = make_user()
    outside_platform_admin = make_user(platform_admin=True)
    ineligible_admin = make_user(email_verified=False)
    add_membership(db, organization, admin, role="admin")
    add_membership(db, organization, moderator, role="moderator")
    add_membership(db, organization, member, role="member")
    add_membership(db, organization, ineligible_admin, role="admin")
    make_org(owner=outside_platform_admin)

    url = f"/api/v1/organizations/{organization.id}/announcements"
    owner_post = client.post(url, json=announcement_payload("Owner post"), headers=auth(owner, token_for))
    admin_post = client.post(url, json=announcement_payload("Admin post"), headers=auth(admin, token_for))
    assert owner_post.status_code == admin_post.status_code == 201

    for user in (moderator, member, outside_platform_admin):
        response = client.post(url, json=announcement_payload(), headers=auth(user, token_for))
        assert response.status_code == 403

    ineligible_response = client.post(
        url, json=announcement_payload(), headers=auth(ineligible_admin, token_for)
    )
    assert ineligible_response.status_code == 403
    assert ineligible_response.json()["error"]["code"] == "plm_email_required"

    pending_owner = make_user()
    pending_org = make_org(owner=pending_owner, accreditation_status="pending")
    pending_response = client.post(
        f"/api/v1/organizations/{pending_org.id}/announcements",
        json=announcement_payload(),
        headers=auth(pending_owner, token_for),
    )
    assert pending_response.status_code == 403
    assert pending_response.json()["error"]["code"] == "organization_forbidden"


def test_hidden_announcement_cannot_be_edited_but_owner_can_remove_it_and_foreign_managers_cannot(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    foreign_owner = make_user()
    organization = make_org(owner=owner)
    foreign_organization = make_org(owner=foreign_owner)
    hidden = seed_announcement(db, organization, owner, "Platform-hidden post", hidden=True)
    visible = seed_announcement(db, organization, owner, "Other club's public post")

    owner_headers = auth(owner, token_for)
    detail_url = f"/api/v1/announcements/{hidden.id}"
    cannot_edit = client.patch(
        detail_url,
        json={"title": "Attempted hidden edit"},
        headers={**owner_headers, "If-Match": '"1"'},
    )
    assert cannot_edit.status_code == 409
    assert db.get(Announcement, hidden.id).title == "Platform-hidden post"

    removed = client.delete(detail_url, headers={**owner_headers, "If-Match": '"1"'})
    assert removed.status_code == 204
    assert removed.headers["etag"] == '"2"'
    assert client.get(detail_url, headers=owner_headers).status_code == 404
    history = client.get(f"{detail_url}/history", headers=owner_headers)
    assert history.status_code == 200
    assert [item["action"] for item in history.json()] == ["publish", "remove"]

    foreign_headers = auth(foreign_owner, token_for)
    assert client.get(f"/api/v1/announcements/{visible.id}/history", headers=foreign_headers).status_code == 404
    assert client.patch(
        f"/api/v1/announcements/{visible.id}",
        json={"title": "Cross-organization edit"},
        headers={**foreign_headers, "If-Match": '"1"'},
    ).status_code == 404
    assert client.get(
        f"/api/v1/organizations/{organization.id}/announcements/manage",
        headers=foreign_headers,
    ).status_code == 403
    assert foreign_organization.id != organization.id


def test_create_retry_patch_etags_revisions_and_idempotent_removal(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    url = f"/api/v1/organizations/{organization.id}/announcements"
    headers = auth(owner, token_for)
    key = uuid4()
    payload = announcement_payload("  Original title  ", key=key, body="  Original body  ")

    created = client.post(url, json=payload, headers=headers)
    assert created.status_code == 201
    post_id = created.json()["id"]
    assert created.json()["title"] == "Original title"
    assert created.json()["body"] == "Original body"
    assert created.headers["etag"] == '"1"'

    retry = client.post(url, json=payload, headers=headers)
    assert retry.status_code == 201
    assert retry.json()["id"] == post_id
    conflict = client.post(
        url,
        json=announcement_payload("Different content", key=key),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    detail_url = f"/api/v1/announcements/{post_id}"
    assert client.patch(detail_url, json={"title": "No ETag"}, headers=headers).status_code == 409
    assert client.patch(
        detail_url, json={"title": "Stale"}, headers={**headers, "If-Match": '"0"'}
    ).status_code == 409
    assert client.patch(
        detail_url, json={"title": None}, headers={**headers, "If-Match": '"1"'}
    ).status_code == 422
    assert client.patch(
        detail_url, json={"audience": None}, headers={**headers, "If-Match": '"1"'}
    ).status_code == 422

    no_op = client.patch(
        detail_url, json={"title": "Original title"}, headers={**headers, "If-Match": '"1"'}
    )
    assert no_op.status_code == 200
    assert no_op.json()["version"] == 1
    assert no_op.json()["edited_at"] is None

    edited = client.patch(
        detail_url, json={"title": "Updated title"}, headers={**headers, "If-Match": '"1"'}
    )
    assert edited.status_code == 200
    assert edited.headers["etag"] == '"2"'
    assert edited.json()["version"] == 2
    assert edited.json()["title"] == "Updated title"
    assert edited.json()["body"] == "Original body"
    assert edited.json()["audience"] == "public"
    assert edited.json()["edited_at"] is not None

    unchanged = client.patch(
        detail_url, json={"title": "Updated title"}, headers={**headers, "If-Match": '"2"'}
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["version"] == 2

    stale_delete = client.delete(detail_url, headers={**headers, "If-Match": '"1"'})
    assert stale_delete.status_code == 409
    deleted = client.delete(detail_url, headers={**headers, "If-Match": '"2"'})
    assert deleted.status_code == 204
    assert deleted.headers["etag"] == '"3"'
    repeated = client.delete(detail_url, headers={**headers, "If-Match": '"1"'})
    assert repeated.status_code == 204
    assert repeated.headers["etag"] == '"3"'
    assert client.get(detail_url, headers=headers).status_code == 404

    revisions = db.scalars(
        select(AnnouncementRevision)
        .where(AnnouncementRevision.announcement_id == post_id)
        .order_by(AnnouncementRevision.version)
    ).all()
    assert [(revision.version, revision.action) for revision in revisions] == [
        (1, "publish"),
        (2, "edit"),
        (3, "remove"),
    ]
    row = db.get(Announcement, post_id)
    assert row is not None and row.removed_at is not None and row.body is None
    assert db.scalar(
        select(func.count(AnnouncementReaction.id)).where(AnnouncementReaction.announcement_id == post_id)
    ) == 0


def test_pending_person_review_blocks_new_and_changed_announcements_but_not_cleanup(
    client, db, make_user, make_org, make_event, token_for
):
    from app.domains.announcements.moderation_models import AnnouncementReport

    owner = make_user()
    reporter = make_user()
    organization = make_org(owner=owner)
    url = f"/api/v1/organizations/{organization.id}/announcements"
    headers = auth(owner, token_for)
    key = uuid4()
    payload = announcement_payload("Existing post", key=key)
    created = client.post(url, json=payload, headers=headers)
    assert created.status_code == 201
    post_id = created.json()["id"]
    event = make_event(org=organization)
    db.add(
        ContentReport(
            id=uid(),
            event_id=event.id,
            org_id=organization.id,
            reporter_id=reporter.id,
            subject_user_id=owner.id,
            kind="person",
            target_id=owner.id,
            reason="other",
            status="open",
            stage="platform",
            deadline=now() + timedelta(days=2),
        )
    )
    evidence = "Retained snapshot, independent of later post removal"
    post_report = AnnouncementReport(
        id=uid(),
        announcement_id=post_id,
        org_id=organization.id,
        reporter_id=reporter.id,
        subject_user_id=owner.id,
        reason="other",
        status="open",
        reported_version=1,
        evidence=evidence,
        deadline=now() + timedelta(days=2),
    )
    db.add(post_report)
    db.commit()

    same_retry = client.post(url, json=payload, headers=headers)
    assert same_retry.status_code == 201
    assert same_retry.json()["id"] == post_id
    different_retry = client.post(
        url, json=announcement_payload("Different post", key=key), headers=headers
    )
    assert different_retry.status_code == 409
    blocked_create = client.post(url, json=announcement_payload("New post"), headers=headers)
    assert blocked_create.status_code == 403
    assert blocked_create.json()["error"]["code"] == "personal_review_pending"

    detail_url = f"/api/v1/announcements/{post_id}"
    no_op = client.patch(
        detail_url,
        json={"title": "Existing post"},
        headers={**headers, "If-Match": '"1"'},
    )
    assert no_op.status_code == 200
    blocked_edit = client.patch(
        detail_url,
        json={"body": "Changed while restricted"},
        headers={**headers, "If-Match": '"1"'},
    )
    assert blocked_edit.status_code == 403
    assert blocked_edit.json()["error"]["code"] == "personal_review_pending"

    removed = client.delete(detail_url, headers={**headers, "If-Match": '"1"'})
    assert removed.status_code == 204
    retained = db.execute(
        select(AnnouncementReport.reported_version, AnnouncementReport.evidence)
        .where(AnnouncementReport.id == post_report.id)
    ).one()
    assert retained == (1, evidence)
    assert db.get(Announcement, post_id).body is None
    assert [item["action"] for item in client.get(
        f"{detail_url}/history", headers=headers
    ).json()] == ["publish", "remove"]


def test_platform_admin_and_stale_or_ineligible_members_do_not_gain_private_visibility(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    platform_admin = make_user(platform_admin=True)
    make_org(owner=platform_admin)
    ineligible_member = make_user(email_verified=False)
    member = make_user()
    member_post = seed_announcement(
        db, organization, owner, "Private membership notice", audience="members"
    )
    public_post = seed_announcement(db, organization, owner, "Public notice")
    membership = add_membership(db, organization, member, role="member")
    add_membership(db, organization, ineligible_member, role="admin")

    private_url = f"/api/v1/announcements/{member_post.id}"
    reactions_url = f"{private_url}/reactions"
    collection_url = f"/api/v1/organizations/{organization.id}/announcements"
    for outsider in (platform_admin, ineligible_member):
        headers = auth(outsider, token_for)
        assert client.get(private_url, headers=headers).status_code == 404
        assert client.get(reactions_url, headers=headers).status_code == 404
        assert client.post(reactions_url, json={"reaction": "support"}, headers=headers).status_code == 404
        listing = client.get(collection_url, headers=headers)
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [public_post.id]

    assert client.get(private_url, headers=auth(member, token_for)).status_code == 200
    membership.active = False
    db.commit()
    assert client.get(private_url, headers=auth(member, token_for)).status_code == 404
    assert client.get(reactions_url, headers=auth(member, token_for)).status_code == 404


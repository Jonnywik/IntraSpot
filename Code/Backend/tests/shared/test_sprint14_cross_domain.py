"""Cross-domain privacy, report retention, and moderation contract checks."""

from datetime import timedelta
import json
import os
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import ROOT, get_settings
from app.db.models import now, uid
from app.domains.announcements.models import (
    Announcement,
    AnnouncementReaction,
    AnnouncementRevision,
)
from app.domains.announcements.moderation_models import (
    AnnouncementReport,
    AnnouncementReportDecision,
)
from app.domains.events.models import Event
from app.domains.moderation.models import ContentReport
from app.domains.moderation.service import has_pending_person_report
from app.domains.organizations.models import OrgMembership
from app.notifications import Notification
from app.domains.registrations.models import Registration
from app.domains.social.schemas import REACTION_KINDS


API = "/api/v1"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def add_membership(db, organization, user, role="member", *, active=True):
    grant = OrgMembership(
        id=uid(),
        org_id=organization.id,
        user_id=user.id,
        role=role,
        active=active,
    )
    db.add(grant)
    db.commit()
    return grant


def publish(client, token, organization, title, body, audience="members", key=None):
    return client.post(
        f"{API}/organizations/{organization.id}/announcements",
        headers=auth(token),
        json={
            "title": title,
            "body": body,
            "audience": audience,
            "client_key": key or str(uuid4()),
        },
    )


def report(client, token, announcement_id, reason="spam"):
    return client.post(
        f"{API}/announcements/{announcement_id}/reports",
        headers=auth(token),
        json={"reason": reason},
    )


def evidence_snapshot(value, title, body):
    assert value is not None
    assert json.loads(value) == {"title": title, "body": body}


def test_public_and_member_announcement_access_hides_direct_ids_reactions_and_history(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    member = make_user()
    moderator = make_user()
    outsider = make_user()
    ineligible_member = make_user(email="fictional-ineligible@example.test")
    platform_admin = make_user(platform_admin=True)
    add_membership(db, organization, member)
    add_membership(db, organization, moderator, role="moderator")
    add_membership(db, organization, ineligible_member)
    other_org_member = make_user()
    other_organization = make_org(owner=make_user())
    add_membership(db, other_organization, other_org_member)

    public_title = "Fictional public announcement title"
    public_body = "Fictional public body visible to guests."
    private_title = "Fictional members-only announcement title"
    private_body = "PRIVATE SPRINT14 BODY MARKER"
    public = publish(
        client, token_for(owner), organization, public_title, public_body, "public"
    )
    private = publish(
        client, token_for(owner), organization, private_title, private_body, "members"
    )
    assert public.status_code == private.status_code == 201

    # Make the private row newest so a list implementation that filters after
    # applying LIMIT would incorrectly return an empty guest page.
    public_row = db.get(Announcement, public.json()["id"])
    private_row = db.get(Announcement, private.json()["id"])
    private_row.created_at = public_row.created_at + timedelta(minutes=1)
    private_row.updated_at = private_row.created_at
    db.commit()
    assert db.scalar(select(func.count(Notification.id))) == 0

    public_list = client.get(
        f"{API}/organizations/{organization.id}/announcements?limit=1&offset=0"
    )
    assert public_list.status_code == 200
    assert public_list.headers["cache-control"] == "private, no-store"
    assert "Authorization" in public_list.headers["vary"]
    assert [item["id"] for item in public_list.json()] == [public.json()["id"]]
    public_fields = {
        "id", "org_id", "organization_name", "title", "body", "audience",
        "version", "created_at", "updated_at", "edited_at", "state",
    }
    assert set(public_list.json()[0]) == public_fields
    assert "created_by" not in public_list.json()[0]
    assert "author_id" not in public_list.json()[0]
    guest_detail = client.get(f"{API}/announcements/{public.json()['id']}")
    assert guest_detail.status_code == 200
    assert guest_detail.json()["title"] == public_title

    member_detail = client.get(
        f"{API}/announcements/{private.json()['id']}",
        headers=auth(token_for(member)),
    )
    assert member_detail.status_code == 200
    assert member_detail.json()["body"] == private_body
    member_list = client.get(
        f"{API}/organizations/{organization.id}/announcements",
        headers=auth(token_for(member)),
    )
    assert {item["id"] for item in member_list.json()} == {
        public.json()["id"], private.json()["id"]
    }

    for token in (
        None,
        token_for(outsider),
        token_for(other_org_member),
        token_for(ineligible_member),
        token_for(platform_admin),
    ):
        headers = auth(token) if token else {}
        for suffix in ("", "/reactions"):
            response = client.get(
                f"{API}/announcements/{private.json()['id']}{suffix}",
                headers=headers,
            )
            assert response.status_code == 404
            assert private_title not in response.text
            assert private_body not in response.text
            assert "counts" not in response.text

    denied_reaction = client.post(
        f"{API}/announcements/{private.json()['id']}/reactions",
        headers=auth(token_for(outsider)),
        json={"reaction": "support"},
    )
    denied_reaction_status = denied_reaction.status_code
    assert denied_reaction_status == 404
    ineligible_private_reaction = client.post(
        f"{API}/announcements/{private.json()['id']}/reactions",
        headers=auth(token_for(ineligible_member)),
        json={"reaction": "support"},
    )
    ineligible_private_reaction_status = ineligible_private_reaction.status_code
    assert ineligible_private_reaction_status == 404
    assert private_title not in ineligible_private_reaction.text
    assert private_body not in ineligible_private_reaction.text
    denied_history = client.get(
        f"{API}/announcements/{private.json()['id']}/history",
        headers=auth(token_for(outsider)),
    )
    assert denied_history.status_code == 404
    assert private_title not in denied_history.text
    assert private_body not in denied_history.text

    member_history = client.get(
        f"{API}/announcements/{private.json()['id']}/history",
        headers=auth(token_for(member)),
    )
    assert member_history.status_code == 404
    assert private_title not in member_history.text
    guest_history = client.get(f"{API}/announcements/{private.json()['id']}/history")
    assert guest_history.status_code == 401
    assert private_title not in guest_history.text

    staff_detail = client.get(
        f"{API}/announcements/{private.json()['id']}",
        headers=auth(token_for(moderator)),
    )
    assert staff_detail.status_code == 200
    staff_reactions = client.get(
        f"{API}/announcements/{private.json()['id']}/reactions",
        headers=auth(token_for(moderator)),
    )
    assert staff_reactions.status_code == 200
    summary = staff_reactions.json()
    assert set(summary) == {"counts", "total", "mine", "can_react"}
    assert set(summary["counts"]) == {
        "interested", "excited", "support", "kudos", "wow", "relate"
    }
    assert not {"user_id", "user_ids", "reactors", "email", "nickname"} & set(summary)

    moderator_create = publish(
        client, token_for(moderator), organization,
        "Moderator must not author", "No moderator authoring.", "public",
    )
    platform_create = publish(
        client, token_for(platform_admin), organization,
        "Platform admin without membership", "No platform-only authoring.", "public",
    )
    assert moderator_create.status_code == platform_create.status_code == 403
    outsider_report = report(client, token_for(outsider), private.json()["id"])
    outsider_report_status = outsider_report.status_code
    assert outsider_report_status == 404
    ineligible_public_report = report(
        client, token_for(ineligible_member), public.json()["id"]
    )
    ineligible_public_report_status = ineligible_public_report.status_code
    assert ineligible_public_report_status == 403

    pending_owner = make_user()
    pending_org = make_org(owner=pending_owner, accreditation_status="pending")
    pending_post = Announcement(
        id=uid(),
        org_id=pending_org.id,
        created_by=pending_owner.id,
        title="Pending organization content marker",
        body="Pending organization body marker",
        audience="public",
        version=1,
        client_key=uid(),
        create_hash="a" * 64,
        created_at=now(),
        updated_at=now(),
    )
    db.add(pending_post)
    db.commit()
    pending_list = client.get(f"{API}/organizations/{pending_org.id}/announcements")
    pending_detail = client.get(f"{API}/announcements/{pending_post.id}")
    assert pending_list.status_code == pending_detail.status_code == 404
    assert "Pending organization content marker" not in pending_detail.text


def test_membership_exit_revokes_private_reads_and_writes_but_keeps_private_receipt(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    member = make_user()
    grant = add_membership(db, organization, member)
    created = publish(
        client,
        token_for(owner),
        organization,
        "Fictional private club update",
        "MEMBERSHIP EXIT PRIVATE MARKER",
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    second_private = publish(
        client,
        token_for(owner),
        organization,
        "Fictional second private notice",
        "SECOND PRIVATE REPORT WRITE MARKER",
    )
    assert second_private.status_code == 201
    member_headers = auth(token_for(member))

    assert client.get(f"{API}/announcements/{post_id}", headers=member_headers).status_code == 200
    assert client.post(
        f"{API}/announcements/{post_id}/reactions",
        headers=member_headers,
        json={"reaction": "support"},
    ).status_code == 200
    first_report = report(client, token_for(member), post_id)
    retry_report = report(client, token_for(member), post_id, reason="other")
    assert first_report.status_code == retry_report.status_code == 201
    assert retry_report.json() == first_report.json()
    report_id = first_report.json()["id"]
    received_key = f"announcement_report:{report_id}:received:%"
    notice_count = db.scalar(
        select(func.count(Notification.id)).where(Notification.dedupe_key.like(received_key))
    )
    assert notice_count > 0

    left = client.post(
        f"{API}/organizations/{organization.id}/membership/leave",
        headers=member_headers,
        json={"client_key": str(uuid4())},
    )
    assert left.status_code == 200
    assert left.json()["active"] is False
    db.expire_all()
    assert db.get(OrgMembership, grant.id).active is False

    assert client.get(
        f"{API}/organizations/{organization.id}/announcements", headers=member_headers
    ).json() == []
    for suffix in ("", "/reactions", "/history"):
        response = client.get(
            f"{API}/announcements/{post_id}{suffix}", headers=member_headers
        )
        assert response.status_code == 404
        assert "MEMBERSHIP EXIT PRIVATE MARKER" not in response.text
    denied_write = client.post(
        f"{API}/announcements/{post_id}/reactions",
        headers=member_headers,
        json={"reaction": None},
    )
    assert denied_write.status_code == 404
    denied_report = report(client, token_for(member), second_private.json()["id"])
    assert denied_report.status_code == 404

    receipts = client.get(f"{API}/me/announcement-reports", headers=member_headers)
    assert receipts.status_code == 200
    assert len(receipts.json()) == 1
    assert receipts.json()[0]["id"] == report_id
    assert set(receipts.json()[0]) == {"id", "announcement_id", "org_id", "status", "deadline"}
    assert "MEMBERSHIP EXIT PRIVATE MARKER" not in receipts.text
    assert db.scalar(
        select(func.count(Notification.id)).where(Notification.dedupe_key.like(received_key))
    ) == notice_count
    assert db.scalar(select(func.count(AnnouncementReport.id))) == 1


def test_reaction_retries_replace_one_row_and_never_change_event_attendance(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization, capacity=1, interest_count=11)
    viewer = make_user()
    created = publish(
        client,
        token_for(owner),
        organization,
        "Fictional public reactions post",
        "Aggregate counts only.",
        "public",
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    headers = auth(token_for(viewer))
    baseline_registrations = db.scalar(
        select(func.count(Registration.id)).where(Registration.event_id == event.id)
    )

    for kind in REACTION_KINDS:
        first = client.post(
            f"{API}/announcements/{post_id}/reactions",
            headers=headers,
            json={"reaction": kind},
        )
        retry = client.post(
            f"{API}/announcements/{post_id}/reactions",
            headers=headers,
            json={"reaction": kind},
        )
        assert first.status_code == retry.status_code == 200
        assert retry.json()["mine"] == kind
        assert retry.json()["total"] == 1
        assert retry.json()["counts"][kind] == 1
        assert db.scalar(
            select(func.count(AnnouncementReaction.id)).where(
                AnnouncementReaction.announcement_id == post_id
            )
        ) == 1

    removed = client.post(
        f"{API}/announcements/{post_id}/reactions",
        headers=headers,
        json={"reaction": None},
    )
    assert removed.status_code == 200
    assert removed.json()["mine"] is None
    assert removed.json()["total"] == 0
    assert db.scalar(
        select(func.count(AnnouncementReaction.id)).where(
            AnnouncementReaction.announcement_id == post_id
        )
    ) == 0

    db.expire_all()
    assert db.get(Event, event.id).interest_count == 11
    assert db.scalar(
        select(func.count(Registration.id)).where(Registration.event_id == event.id)
    ) == baseline_registrations


def test_author_retries_and_mutations_preserve_exact_open_report_evidence(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    org_admin = make_user()
    organization = make_org(owner=owner)
    add_membership(db, organization, org_admin, role="admin")
    reporter = make_user()
    title = "Fictional report snapshot title"
    body = "EXACT ORIGINAL REPORT BODY"
    key = str(uuid4())
    created = publish(client, token_for(owner), organization, title, body, "public", key)
    replay = publish(client, token_for(owner), organization, title, body, "public", key)
    changed_replay = publish(
        client, token_for(owner), organization, title, "Changed payload", "public", key
    )
    assert created.status_code == replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    assert changed_replay.status_code == 409
    post_id = created.json()["id"]
    create_hash = db.get(Announcement, post_id).create_hash
    assert db.scalar(
        select(func.count(Announcement.id)).where(Announcement.id == post_id)
    ) == 1

    admin_post = publish(
        client,
        token_for(org_admin),
        organization,
        "Fictional admin announcement",
        "An active organization admin may manage posts.",
        "public",
    )
    assert admin_post.status_code == 201
    admin_edit = client.patch(
        f"{API}/announcements/{admin_post.json()['id']}",
        headers=auth(token_for(org_admin)) | {"If-Match": '"1"'},
        json={"body": "Updated by the organization admin."},
    )
    assert admin_edit.status_code == 200 and admin_edit.json()["version"] == 2
    admin_remove = client.delete(
        f"{API}/announcements/{admin_post.json()['id']}",
        headers=auth(token_for(org_admin)) | {"If-Match": '"2"'},
    )
    assert admin_remove.status_code == 204

    own_report = report(client, token_for(owner), post_id)
    assert own_report.status_code == 403
    first_report = report(client, token_for(reporter), post_id)
    assert first_report.status_code == 201
    report_id = first_report.json()["id"]
    stored_report = db.get(AnnouncementReport, report_id)
    assert stored_report.reported_version == 1
    evidence_snapshot(stored_report.evidence, title, body)
    notices_before_retry = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.dedupe_key.like(f"announcement_report:{report_id}:received:%")
        )
    )
    retry_after_edit = report(client, token_for(reporter), post_id, reason="other")
    assert retry_after_edit.status_code == 201
    assert retry_after_edit.json() == first_report.json()
    assert db.scalar(
        select(func.count(Notification.id)).where(
            Notification.dedupe_key.like(f"announcement_report:{report_id}:received:%")
        )
    ) == notices_before_retry

    unchanged = client.patch(
        f"{API}/announcements/{post_id}",
        headers=auth(token_for(owner)) | {"If-Match": '"1"'},
        json={"title": title, "body": body, "audience": "public"},
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["version"] == 1
    assert unchanged.json()["edited_at"] is None
    assert db.scalar(
        select(func.count(AnnouncementRevision.id)).where(
            AnnouncementRevision.announcement_id == post_id
        )
    ) == 1

    edited_title = "Fictional revised announcement title"
    edited_body = "UPDATED BODY AFTER THE REPORT"
    edited = client.patch(
        f"{API}/announcements/{post_id}",
        headers=auth(token_for(owner)) | {"If-Match": '"1"'},
        json={"title": edited_title, "body": edited_body},
    )
    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert edited.json()["edited_at"] is not None
    stale = client.patch(
        f"{API}/announcements/{post_id}",
        headers=auth(token_for(owner)) | {"If-Match": '"1"'},
        json={"body": "STALE WRITE MUST NOT LAND"},
    )
    assert stale.status_code == 409
    assert client.get(f"{API}/announcements/{post_id}").json()["body"] == edited_body

    post = db.get(Announcement, post_id)
    report_row = db.get(AnnouncementReport, report_id)
    assert post.create_hash == create_hash
    assert post.version == 2
    assert report_row.status == "open"
    assert report_row.reported_version == 1
    evidence_snapshot(report_row.evidence, title, body)
    assert client.get(f"{API}/announcements/{post_id}").status_code == 200

    removed = client.delete(
        f"{API}/announcements/{post_id}",
        headers=auth(token_for(owner)) | {"If-Match": '"2"'},
    )
    assert removed.status_code == 204
    db.expire_all()
    post = db.get(Announcement, post_id)
    report_row = db.get(AnnouncementReport, report_id)
    assert post is not None and post.removed_at is not None and post.body is None
    assert post.version == 3
    assert report_row.status == "open"
    evidence_snapshot(report_row.evidence, title, body)
    assert client.get(f"{API}/announcements/{post_id}").status_code == 404

    repeated_remove = client.delete(
        f"{API}/announcements/{post_id}",
        # Retry the exact request a client would resend after losing the 204.
        # Its original precondition is now stale, but the completed delete is
        # an idempotent success and must not append another revision.
        headers=auth(token_for(owner)) | {"If-Match": '"2"'},
    )
    assert repeated_remove.status_code == 204
    revisions = list(db.scalars(
        select(AnnouncementRevision)
        .where(AnnouncementRevision.announcement_id == post_id)
        .order_by(AnnouncementRevision.version)
    ))
    assert [(row.version, row.action, row.actor_id) for row in revisions] == [
        (1, "publish", owner.id),
        (2, "edit", owner.id),
        (3, "remove", owner.id),
    ]
    assert db.scalar(
        select(func.count(AnnouncementReportDecision.id)).where(
            AnnouncementReportDecision.report_id == report_id
        )
    ) == 0


def test_personal_communication_restriction_blocks_new_and_changed_posts_but_allows_cleanup(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    reporter = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization)
    title = "Fictional post retained during personal review"
    body = "Exact announcement evidence survives owner cleanup."
    create_key = str(uuid4())
    created = publish(
        client, token_for(owner), organization, title, body, "public", key=create_key
    )
    assert created.status_code == 201
    post_id = created.json()["id"]

    receipt = report(client, token_for(reporter), post_id, "other")
    assert receipt.status_code == 201
    report_row = db.get(AnnouncementReport, receipt.json()["id"])
    evidence_snapshot(report_row.evidence, title, body)

    db.add(ContentReport(
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
    ))
    db.commit()

    owner_headers = auth(token_for(owner))
    me = client.get(f"{API}/me", headers=owner_headers)
    assert me.status_code == 200 and me.json()["communication_restricted"] is True
    same_create_retry = publish(
        client, token_for(owner), organization, title, body, "public",
        key=create_key,
    )
    assert same_create_retry.status_code == 201
    assert same_create_retry.json()["id"] == post_id
    blocked_create = publish(
        client, token_for(owner), organization,
        "Blocked announcement", "Must not be published.", "public",
    )
    assert blocked_create.status_code == 403
    assert blocked_create.json()["error"]["code"] == "personal_review_pending"

    no_op = client.patch(
        f"{API}/announcements/{post_id}",
        headers=owner_headers | {"If-Match": '"1"'},
        json={"title": title},
    )
    assert no_op.status_code == 200 and no_op.json()["version"] == 1
    blocked_edit = client.patch(
        f"{API}/announcements/{post_id}",
        headers=owner_headers | {"If-Match": '"1"'},
        json={"body": "Blocked body change."},
    )
    assert blocked_edit.status_code == 403
    assert blocked_edit.json()["error"]["code"] == "personal_review_pending"

    removed = client.delete(
        f"{API}/announcements/{post_id}",
        headers=owner_headers | {"If-Match": '"1"'},
    )
    assert removed.status_code == 204
    db.expire_all()
    assert db.get(Announcement, post_id).body is None
    retained_report = db.get(AnnouncementReport, receipt.json()["id"])
    assert retained_report.status == "open"
    evidence_snapshot(retained_report.evidence, title, body)


def test_platform_review_is_event_independent_audited_and_idempotent(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    reporter = make_user()
    second_reporter = make_user()
    platform_admin = make_user(platform_admin=True)
    organization = make_org(owner=owner)
    org_admin = make_user()
    add_membership(db, organization, org_admin, role="admin")
    event_count = db.scalar(select(func.count(Event.id)))
    posts = {}
    reports = {}
    for name in ("restore", "remove", "dismiss", "owner_remove", "multiple"):
        created = publish(
            client,
            token_for(owner),
            organization,
            f"Fictional {name} review post",
            f"Original evidence for {name}.",
            "public",
        )
        assert created.status_code == 201
        posts[name] = created.json()
        response = report(client, token_for(reporter), created.json()["id"], "harassment")
        assert response.status_code == 201
        reports[name] = response.json()
        if name == "multiple":
            second_response = report(
                client, token_for(second_reporter), created.json()["id"], "other"
            )
            assert second_response.status_code == 201
            reports["multiple_second"] = second_response.json()

    forbidden_queue = client.get(
        f"{API}/moderation/announcement-reports", headers=auth(token_for(owner))
    )
    assert forbidden_queue.status_code == 403
    event_queue = client.get(
        f"{API}/moderation/reports?org_id={organization.id}",
        headers=auth(token_for(owner)),
    )
    assert event_queue.status_code == 200 and event_queue.json() == []

    queue = client.get(
        f"{API}/moderation/announcement-reports",
        headers=auth(token_for(platform_admin)),
    )
    assert queue.status_code == 200
    assert {row["id"] for row in queue.json()} == {
        row["id"] for row in reports.values()
    }
    assert all(row["evidence"] for row in queue.json())

    restore_report = reports["restore"]
    restore_post_id = posts["restore"]["id"]
    hidden = client.post(
        f"{API}/moderation/announcement-reports/{restore_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"1"'},
        json={"action": "hide"},
    )
    assert hidden.status_code == 200
    assert (hidden.json()["status"], hidden.json()["post_state"], hidden.json()["post_version"]) == (
        "hidden", "hidden", 2
    )
    assert hidden.json()["evidence"] is None
    assert client.get(f"{API}/announcements/{restore_post_id}").status_code == 404
    hidden_reactions = client.get(f"{API}/announcements/{restore_post_id}/reactions")
    assert hidden_reactions.status_code == 404 and "counts" not in hidden_reactions.text
    for manager in (owner, org_admin, platform_admin):
        hidden_detail = client.get(
            f"{API}/announcements/{restore_post_id}",
            headers=auth(token_for(manager)),
        )
        assert hidden_detail.status_code == 404
        assert "Fictional restore review post" not in hidden_detail.text
        if manager in (owner, org_admin):
            continue
        hidden_history = client.get(
            f"{API}/announcements/{restore_post_id}/history",
            headers=auth(token_for(manager)),
        )
        hidden_history_status = hidden_history.status_code
        assert hidden_history_status == 404
        assert "Original evidence for restore." not in hidden_history.text
    for manager in (owner, org_admin):
        hidden_history = client.get(
            f"{API}/announcements/{restore_post_id}/history",
            headers=auth(token_for(manager)),
        )
        hidden_history_status = hidden_history.status_code
        assert hidden_history_status == 200
        assert [item["action"] for item in hidden_history.json()] == ["publish", "hide"]
    blocked_owner_edit = client.patch(
        f"{API}/announcements/{restore_post_id}",
        headers=auth(token_for(owner)) | {"If-Match": '"2"'},
        json={"body": "Owner cannot edit hidden text."},
    )
    assert blocked_owner_edit.status_code == 409

    # A hidden case can be restored after its evidence deadline; the text is
    # immutable while hidden, and restoration does not recreate the snapshot.
    restore_row = db.get(AnnouncementReport, restore_report["id"])
    restore_row.deadline = now() - timedelta(seconds=1)
    db.commit()
    restored = client.post(
        f"{API}/moderation/announcement-reports/{restore_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"2"'},
        json={"action": "restore"},
    )
    assert restored.status_code == 200
    assert (restored.json()["status"], restored.json()["post_state"], restored.json()["post_version"]) == (
        "restored", "visible", 3
    )
    restore_retry = client.post(
        f"{API}/moderation/announcement-reports/{restore_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"3"'},
        json={"action": "restore"},
    )
    assert restore_retry.status_code == 200
    assert restore_retry.json()["post_version"] == 3

    remove_report = reports["remove"]
    remove_post_id = posts["remove"]["id"]
    hidden_for_removal = client.post(
        f"{API}/moderation/announcement-reports/{remove_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"1"'},
        json={"action": "hide"},
    )
    assert hidden_for_removal.status_code == 200
    removed = client.post(
        f"{API}/moderation/announcement-reports/{remove_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"2"'},
        json={"action": "remove"},
    )
    assert removed.status_code == 200
    assert (removed.json()["status"], removed.json()["post_state"], removed.json()["post_version"]) == (
        "removed", "removed", 3
    )
    remove_retry = client.post(
        f"{API}/moderation/announcement-reports/{remove_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"3"'},
        json={"action": "remove"},
    )
    assert remove_retry.status_code == 200
    assert remove_retry.json()["post_version"] == 3
    cannot_restore_removed = client.post(
        f"{API}/moderation/announcement-reports/{remove_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"3"'},
        json={"action": "restore"},
    )
    assert cannot_restore_removed.status_code == 409
    assert client.get(f"{API}/announcements/{remove_post_id}").status_code == 404
    removed_reactions = client.get(f"{API}/announcements/{remove_post_id}/reactions")
    assert removed_reactions.status_code == 404 and "counts" not in removed_reactions.text
    for manager in (owner, org_admin, platform_admin):
        removed_detail = client.get(
            f"{API}/announcements/{remove_post_id}",
            headers=auth(token_for(manager)),
        )
        assert removed_detail.status_code == 404
        assert "Fictional remove review post" not in removed_detail.text
        if manager in (owner, org_admin):
            continue
        removed_history = client.get(
            f"{API}/announcements/{remove_post_id}/history",
            headers=auth(token_for(manager)),
        )
        removed_history_status = removed_history.status_code
        assert removed_history_status == 404
        assert "Original evidence for remove." not in removed_history.text
    for manager in (owner, org_admin):
        removed_history = client.get(
            f"{API}/announcements/{remove_post_id}/history",
            headers=auth(token_for(manager)),
        )
        removed_history_status = removed_history.status_code
        assert removed_history_status == 200
        assert [item["action"] for item in removed_history.json()] == [
            "publish", "hide", "remove"
        ]

    dismiss_report = reports["dismiss"]
    dismissed = client.post(
        f"{API}/moderation/announcement-reports/{dismiss_report['id']}/decision",
        headers=auth(token_for(platform_admin)),
        json={"action": "dismiss"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert dismissed.json()["post_state"] == "visible"
    assert dismissed.json()["post_version"] == 1
    assert dismissed.json()["evidence"] is None

    owner_remove_report = reports["owner_remove"]
    owner_remove_id = posts["owner_remove"]["id"]
    owner_remove_hidden = client.post(
        f"{API}/moderation/announcement-reports/{owner_remove_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"1"'},
        json={"action": "hide"},
    )
    assert owner_remove_hidden.status_code == 200
    owner_remove_response = client.delete(
        f"{API}/announcements/{owner_remove_id}",
        headers=auth(token_for(owner)) | {"If-Match": '"2"'},
    )
    assert owner_remove_response.status_code == 204
    owner_removed_row = db.get(Announcement, owner_remove_id)
    assert owner_removed_row.hidden_at is not None
    assert owner_removed_row.removed_at is not None
    assert owner_removed_row.version == 3
    platform_remove_after_owner = client.post(
        f"{API}/moderation/announcement-reports/{owner_remove_report['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"3"'},
        json={"action": "remove"},
    )
    assert platform_remove_after_owner.status_code == 200
    assert platform_remove_after_owner.json()["status"] == "removed"
    assert platform_remove_after_owner.json()["post_version"] == 3

    multiple_post_id = posts["multiple"]["id"]
    multiple_hidden = client.post(
        f"{API}/moderation/announcement-reports/{reports['multiple']['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"1"'},
        json={"action": "hide"},
    )
    assert multiple_hidden.status_code == 200
    same_case_hide_retry = client.post(
        f"{API}/moderation/announcement-reports/{reports['multiple']['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"2"'},
        json={"action": "hide"},
    )
    assert same_case_hide_retry.status_code == 200
    assert same_case_hide_retry.json()["status"] == "hidden"
    assert same_case_hide_retry.json()["post_version"] == 2
    assert db.scalar(select(func.count(AnnouncementReportDecision.id)).where(
        AnnouncementReportDecision.report_id == reports["multiple"]["id"]
    )) == 1

    # A distinct open case cannot piggyback on the existing hidden state and
    # acquire the unique authority to restore that post later.
    second_case_hide = client.post(
        f"{API}/moderation/announcement-reports/{reports['multiple_second']['id']}/decision",
        headers=auth(token_for(platform_admin)) | {"If-Match": '"2"'},
        json={"action": "hide"},
    )
    assert second_case_hide.status_code == 409
    assert second_case_hide.json()["error"]["code"] == "report_decision_conflict"
    assert db.scalar(select(func.count(AnnouncementReportDecision.id)).where(
        AnnouncementReportDecision.report_id == reports["multiple_second"]["id"]
    )) == 0
    other_case = client.get(
        f"{API}/moderation/announcement-reports/{reports['multiple_second']['id']}",
        headers=auth(token_for(platform_admin)),
    )
    assert other_case.status_code == 200
    assert other_case.json()["status"] == "open"
    evidence_snapshot(
        other_case.json()["evidence"],
        posts["multiple"]["title"],
        "Original evidence for multiple.",
    )
    other_case_dismissed = client.post(
        f"{API}/moderation/announcement-reports/{reports['multiple_second']['id']}/decision",
        headers=auth(token_for(platform_admin)),
        json={"action": "dismiss"},
    )
    assert other_case_dismissed.status_code == 200
    assert other_case_dismissed.json()["evidence"] is None
    assert client.get(f"{API}/announcements/{multiple_post_id}").status_code == 404

    for report_id in (
        restore_report["id"], remove_report["id"], dismiss_report["id"],
        owner_remove_report["id"], reports["multiple"]["id"],
        reports["multiple_second"]["id"],
    ):
        detail = client.get(
            f"{API}/moderation/announcement-reports/{report_id}",
            headers=auth(token_for(platform_admin)),
        )
        assert detail.status_code == 200
        assert detail.json()["evidence"] is None
        assert detail.json()["decisions"]
        assert all(item["reviewer_id"] == platform_admin.id for item in detail.json()["decisions"])
        rows = list(db.scalars(select(AnnouncementReportDecision).where(
            AnnouncementReportDecision.report_id == report_id
        )))
        assert all(row.reviewer_id == platform_admin.id for row in rows)

    for post_id, expected_actor_id in (
        (restore_post_id, platform_admin.id),
        (remove_post_id, platform_admin.id),
        (owner_remove_id, owner.id),
    ):
        revisions = list(db.scalars(select(AnnouncementRevision).where(
            AnnouncementRevision.announcement_id == post_id
        ).order_by(AnnouncementRevision.version)))
        assert revisions[-1].actor_id == expected_actor_id

    assert db.scalar(select(func.count(Event.id))) == event_count
    assert db.scalar(select(func.count(ContentReport.id))) == 0
    assert has_pending_person_report(db, owner.id) is False
    owner_state = client.get(f"{API}/me", headers=auth(token_for(owner)))
    assert owner_state.status_code == 200
    assert owner_state.json()["communication_restricted"] is False
    notices = list(db.scalars(select(Notification).where(
        Notification.dedupe_key.like("announcement_report:%")
    )))
    assert notices
    assert all(row.event_id is None and row.org_id == organization.id for row in notices)
    assert len({row.dedupe_key for row in notices}) == len(notices)


def test_report_evidence_expires_at_deadline_and_worker_restart_catches_up_once(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    reporter = make_user()
    platform_admin = make_user(platform_admin=True)
    organization = make_org(owner=owner)
    title = "Fictional expiring report title"
    body = "EXPIRING REPORT EVIDENCE MUST NOT LEAK"
    created = publish(client, token_for(owner), organization, title, body, "public")
    assert created.status_code == 201
    receipt = report(client, token_for(reporter), created.json()["id"], "deception")
    assert receipt.status_code == 201
    report_id = receipt.json()["id"]
    report_row = db.get(AnnouncementReport, report_id)
    assert report_row.deadline == report_row.created_at + timedelta(days=14)
    evidence_snapshot(report_row.evidence, title, body)

    report_row.deadline = now() - timedelta(seconds=1)
    db.commit()
    db.expire_all()
    before_worker = client.get(
        f"{API}/moderation/announcement-reports/{report_id}",
        headers=auth(token_for(platform_admin)),
    )
    assert before_worker.status_code == 200
    assert before_worker.json()["status"] == "open"
    assert before_worker.json()["evidence"] is None
    assert body not in before_worker.text
    assert title not in before_worker.text
    assert db.scalar(select(func.count(AnnouncementReportDecision.id)).where(
        AnnouncementReportDecision.report_id == report_id
    )) == 0

    environment = os.environ.copy()
    environment.update({
        "ENVIRONMENT": "test",
        "FIXTURE_AUTH": "true",
        "DATABASE_URL": get_settings().database_url,
    })
    command = [sys.executable, "-m", "app.deadlines", "--once"]
    try:
        first_run = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=60,
        )
        assert first_run.returncode == 0
        db.expire_all()
        expired = db.get(AnnouncementReport, report_id)
        assert expired.status == "expired"
        assert expired.evidence is None
        assert expired.resolved_at >= expired.deadline
        decision = db.scalar(select(AnnouncementReportDecision).where(
            AnnouncementReportDecision.report_id == report_id
        ))
        assert decision is not None
        assert decision.action == "expire"
        assert decision.reviewer_id is None

        after_worker = client.get(
            f"{API}/moderation/announcement-reports/{report_id}",
            headers=auth(token_for(platform_admin)),
        )
        assert after_worker.status_code == 200
        assert after_worker.json()["evidence"] is None
        assert body not in after_worker.text
        assert client.get(f"{API}/announcements/{created.json()['id']}").status_code == 200

        second_run = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=60,
        )
        assert second_run.returncode == 0
        db.expire_all()
        assert db.get(AnnouncementReport, report_id).status == "expired"
        assert db.scalar(select(func.count(AnnouncementReportDecision.id)).where(
            AnnouncementReportDecision.report_id == report_id
        )) == 1
        expiry_notices = list(db.scalars(select(Notification).where(
            Notification.dedupe_key.like(f"announcement_report:{report_id}:expired:%")
        )))
        assert expiry_notices
        assert len({row.dedupe_key for row in expiry_notices}) == len(expiry_notices)
        assert all(row.event_id is None and row.org_id == organization.id for row in expiry_notices)
    except subprocess.TimeoutExpired:
        assert False, "The isolated deadline worker exceeded its bounded timeout."

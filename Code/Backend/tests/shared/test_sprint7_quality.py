"""Serial PostgreSQL integration regressions for the frozen Sprint 7 contract.

The shared test fixture truncates ``intraspot_mvp_test`` before every test. Run
this module only in the coordinator-granted serial PostgreSQL slot; QA does not
run it independently.
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.db.models import now
from app.domains.organizations.models import OrgMembership
from app.domains.registrations.models import Registration


API = "/api/v1"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REACTIONS = ("interested", "excited", "support", "kudos", "wow", "relate")
CONTENT_ITEM_KEYS = {
    "id",
    "event_id",
    "author_id",
    "author_label",
    "sequence",
    "body",
    "created_at",
    "removed",
    "locally_hidden",
    "mine",
}
REPORT_RECEIPT_KEYS = {
    "id",
    "event_id",
    "kind",
    "target_id",
    "status",
    "stage",
    "deadline",
}
PRIVATE_KEYS = {
    "access_token",
    "age_bracket",
    "avatar_url",
    "body_hash",
    "client_key",
    "email",
    "icebreaker",
    "image",
    "image_key",
    "image_url",
    "nickname",
    "phone",
    "profile_image",
    "profile_image_key",
    "profile_image_url",
    "pronouns",
    "tags",
    "token",
}
WORKER_TIMEOUT_SECONDS = 30


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(client, token_for, event, user, key=None):
    response = client.post(
        f"{API}/events/{event.id}/registrations",
        headers=auth(token_for(user)) | {"Idempotency-Key": key or str(uuid4())},
        json={"persona_shared": False},
    )
    assert response.status_code < 300
    return response.json()


def comment(client, token_for, event, author, body, key=None):
    return client.post(
        f"{API}/events/{event.id}/comments",
        headers=auth(token_for(author)),
        json={"body": body, "client_key": key or str(uuid4())},
    )


def report(client, token_for, event, reporter, kind, target_id, reason="other"):
    return client.post(
        f"{API}/events/{event.id}/reports",
        headers=auth(token_for(reporter)),
        json={"kind": kind, "target_id": target_id, "reason": reason},
    )


def add_org_role(db, organization, user, role):
    db.add(
        OrgMembership(
            id=str(uuid4()),
            org_id=organization.id,
            user_id=user.id,
            role=role,
            active=True,
        )
    )
    db.commit()


def deny(response):
    assert response.status_code in {401, 403, 404}


def nested_keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(item) for item in value)) if value else set()
    return set()


def run_together(actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = [pool.submit(run, action) for action in actions]
        return [future.result(timeout=30) for future in futures]


def guarded_worker_environment():
    env = os.environ.copy()
    if env.get("ENVIRONMENT") != "test" or env.get("FIXTURE_AUTH", "").lower() != "true":
        pytest.fail("Refusing to start the deadline worker outside the guarded test setup.", pytrace=False)
    try:
        target = make_url(env["DATABASE_URL"])
    except Exception:
        pytest.fail("Refusing to start the deadline worker with an invalid database URL.", pytrace=False)
    if not (
        target.drivername == "postgresql+psycopg"
        and target.database == "intraspot_mvp_test"
        and target.host in {"127.0.0.1", "localhost"}
        and target.port == 5433
    ):
        pytest.fail("Refusing to start the deadline worker outside the guarded test database.", pytrace=False)
    return env


def run_deadline_worker():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.deadlines", "--once"],
            cwd=BACKEND_ROOT,
            env=guarded_worker_environment(),
            capture_output=True,
            timeout=WORKER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Deadline worker exceeded its bounded test timeout.", pytrace=False)
    except OSError as exc:
        pytest.fail(f"Deadline worker could not start ({type(exc).__name__}).", pytrace=False)
    if result.returncode != 0:
        pytest.fail(f"Deadline worker exited with status {result.returncode}.", pytrace=False)


def test_guest_comment_privacy_and_six_reactions_do_not_change_capacity(
    client, db, make_event, make_org, make_user, token_for
):
    from app.domains.events.models import Event

    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization, capacity=1, interest_count=7)
    attendee = make_user(nickname="s7-private-attendee-nickname")
    registration = register(client, token_for, event, attendee)
    assert registration["status"] == "confirmed"

    unregistered_author = make_user(
        nickname="s7-private-comment-nickname",
        email="s7-private-comment@students.plm.edu.ph",
    )
    body = "literal <b>campus note</b>"
    created = comment(client, token_for, event, unregistered_author, body)
    assert created.status_code < 300
    assert created.json()["body"] == body

    guest_page = client.get(f"{API}/events/{event.id}/comments")
    assert guest_page.status_code == 200
    item = guest_page.json()["items"][0]
    assert set(item) == CONTENT_ITEM_KEYS
    assert item["body"] == body
    assert item["author_label"] == "PLM member"
    assert item["mine"] is False
    public_json = json.dumps(guest_page.json(), ensure_ascii=False)
    assert unregistered_author.email not in public_json
    assert unregistered_author.nickname not in public_json
    assert {key.lower() for key in nested_keys(guest_page.json())}.isdisjoint(PRIVATE_KEYS)

    guest_summary = client.get(f"{API}/events/{event.id}/reactions")
    assert guest_summary.status_code == 200
    assert set(guest_summary.json()["counts"]) == set(REACTIONS)
    assert guest_summary.json()["counts"] == dict.fromkeys(REACTIONS, 0)
    assert guest_summary.json()["total"] == 0
    assert guest_summary.json()["mine"] is None
    assert guest_summary.json()["can_react"] is False
    deny(
        client.post(
            f"{API}/events/{event.id}/comments",
            json={"body": "guest write", "client_key": str(uuid4())},
        )
    )

    before = client.get(f"{API}/events/{event.id}").json()
    for kind in REACTIONS:
        response = client.post(
            f"{API}/events/{event.id}/reactions",
            headers=auth(token_for(attendee)),
            json={"reaction": kind},
        )
        assert response.status_code == 200
        summary = response.json()
        assert set(summary["counts"]) == set(REACTIONS)
        assert summary["counts"] == {reaction: int(reaction == kind) for reaction in REACTIONS}
        assert summary["total"] == 1
        assert summary["mine"] == kind
        db.refresh(event)
        assert event.interest_count == 7 + int(kind == "interested")

    repeated = client.post(
        f"{API}/events/{event.id}/reactions",
        headers=auth(token_for(attendee)),
        json={"reaction": "relate"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["counts"]["relate"] == 1
    assert repeated.json()["total"] == 1

    removed = client.post(
        f"{API}/events/{event.id}/reactions",
        headers=auth(token_for(attendee)),
        json={"reaction": None},
    )
    assert removed.status_code == 200
    assert removed.json()["total"] == 0
    assert removed.json()["mine"] is None
    db.refresh(event)
    assert event.interest_count == 7

    after = client.get(f"{API}/events/{event.id}").json()
    assert {key: after[key] for key in ("capacity", "confirmed_count", "reserved_count", "remaining_spots")} == {
        key: before[key] for key in ("capacity", "confirmed_count", "reserved_count", "remaining_spots")
    }
    db.expire_all()
    current_registration = db.scalar(
        select(Registration).where(
            Registration.event_id == event.id,
            Registration.user_id == attendee.id,
        )
    )
    assert current_registration.status == "confirmed"
    assert db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == event.id)) == 1

    draft = make_event(org=organization, status="draft", published_at=None)
    assert client.get(f"{API}/events/{draft.id}/comments").status_code == 404


def test_comments_and_reactions_freeze_at_event_start_but_chat_remains_live(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization, capacity=1)
    attendee = make_user()
    register(client, token_for, event, attendee)
    original = comment(client, token_for, event, attendee, "before start")
    assert original.status_code < 300
    reaction = client.post(
        f"{API}/events/{event.id}/reactions",
        headers=auth(token_for(attendee)),
        json={"reaction": "interested"},
    )
    assert reaction.status_code == 200

    event.starts_at = now() - timedelta(seconds=1)
    db.commit()

    assert client.get(f"{API}/events/{event.id}/comments").status_code == 200
    assert comment(client, token_for, event, attendee, "after start").status_code >= 400
    assert client.delete(
        f"{API}/events/{event.id}/comments/{original.json()['id']}",
        headers=auth(token_for(attendee)),
    ).status_code >= 400
    assert client.post(
        f"{API}/events/{event.id}/reactions",
        headers=auth(token_for(attendee)),
        json={"reaction": "excited"},
    ).status_code >= 400
    message = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(attendee)),
        json={"body": "chat remains open until scheduled end", "client_key": str(uuid4())},
    )
    assert message.status_code < 300


def test_concurrent_comment_and_report_retries_create_one_active_row(
    client, db, make_event, make_org, make_user, token_for
):
    from app.domains.moderation.models import ContentReport
    from app.domains.social.models import EventComment

    event = make_event(org=make_org())
    author = make_user()
    reporter = make_user()
    other_reporter = make_user()
    key = str(uuid4())
    body = "same request body"
    comment_requests = [
        lambda: comment(client, token_for, event, author, body, key),
        lambda: comment(client, token_for, event, author, body, key),
    ]
    comment_responses = run_together(comment_requests)
    assert all(response.status_code < 300 for response in comment_responses)
    comment_ids = {response.json()["id"] for response in comment_responses}
    assert len(comment_ids) == 1
    comment_id = comment_ids.pop()
    db.expire_all()
    assert db.scalar(
        select(func.count()).select_from(EventComment).where(
            EventComment.event_id == event.id,
            EventComment.author_id == author.id,
            EventComment.client_key == key,
        )
    ) == 1

    conflicting = comment(client, token_for, event, author, "different body", key)
    assert conflicting.status_code == 409

    report_requests = [
        lambda: report(client, token_for, event, reporter, "comment", comment_id, "spam"),
        lambda: report(client, token_for, event, reporter, "comment", comment_id, "spam"),
    ]
    report_responses = run_together(report_requests)
    assert all(response.status_code < 300 for response in report_responses)
    report_ids = {response.json()["id"] for response in report_responses}
    assert len(report_ids) == 1
    db.expire_all()
    assert db.scalar(
        select(func.count()).select_from(ContentReport).where(
            ContentReport.reporter_id == reporter.id,
            ContentReport.kind == "comment",
            ContentReport.target_id == comment_id,
            ContentReport.status.in_(("open", "escalated")),
        )
    ) == 1

    independent = report(client, token_for, event, other_reporter, "comment", comment_id, "spam")
    assert independent.status_code < 300
    assert independent.json()["id"] not in report_ids


def test_chat_requires_confirmed_registration_and_revokes_on_withdrawal_or_reconfirmation(
    client, db, make_event, make_org, make_user, token_for
):
    message_body = "confirmed attendee message"
    message_key = str(uuid4())
    organization_owner = make_user()
    organization = make_org(owner=organization_owner)
    event = make_event(org=organization, capacity=2)
    withdrawing_user, reconfirming_user = make_user(), make_user()
    register(client, token_for, event, withdrawing_user)
    register(client, token_for, event, reconfirming_user)
    outsider = make_user()

    malformed_id = client.get(
        f"{API}/events/not-a-uuid/chat", headers=auth(token_for(withdrawing_user))
    )
    assert malformed_id.status_code == 422
    deny(client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(outsider))))
    deny(client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(organization_owner))))

    active = client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(withdrawing_user)))
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    assert active.json()["can_send"] is True
    sent = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(withdrawing_user)),
        json={"body": message_body, "client_key": message_key},
    )
    assert sent.status_code == 200

    withdrawn = client.delete(
        f"{API}/events/{event.id}/registrations/me",
        headers=auth(token_for(withdrawing_user)),
    )
    assert withdrawn.status_code < 300
    deny(client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(withdrawing_user))))
    replay_after_withdrawal = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(withdrawing_user)),
        json={"body": message_body, "client_key": message_key},
    )
    assert replay_after_withdrawal.status_code == 403

    change = client.post(
        f"{API}/events/{event.id}/changes",
        headers=auth(token_for(organization_owner)),
        json={
            "reconfirm_deadline": (now() + timedelta(days=1)).isoformat(),
            "venue_name": "Updated fictional courtyard",
        },
    )
    assert change.status_code < 300
    db.expire_all()
    reconfirmation = db.scalar(
        select(Registration).where(
            Registration.event_id == event.id,
            Registration.user_id == reconfirming_user.id,
        )
    )
    assert reconfirmation.status == "reconfirmation_required"
    deny(client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(reconfirming_user))))


def test_chat_archives_read_only_and_expires_at_its_scheduled_72_hour_cutoff(
    client, db, make_event, make_org, make_user, token_for
):
    from app.domains.chat.models import ChatMessage

    event = make_event(org=make_org(), capacity=1)
    attendee = make_user()
    register(client, token_for, event, attendee)
    sent = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(attendee)),
        json={"body": "retention sentinel message", "client_key": str(uuid4())},
    )
    assert sent.status_code < 300
    message_id = sent.json()["id"]
    message_created_at = datetime.fromisoformat(sent.json()["created_at"].replace("Z", "+00:00"))

    event.starts_at = message_created_at - timedelta(hours=2)
    event.ends_at = message_created_at + timedelta(microseconds=1)
    db.commit()
    archived = client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(attendee)))
    assert archived.status_code == 200
    thread = archived.json()
    assert thread["status"] == "archived"
    assert thread["can_send"] is False
    assert thread["items"][0]["body"] == "retention sentinel message"
    deletes_at = datetime.fromisoformat(thread["deletes_at"].replace("Z", "+00:00"))
    db.refresh(event)
    assert deletes_at == event.ends_at + timedelta(hours=72)

    inbox = client.get(f"{API}/me/chats", headers=auth(token_for(attendee)))
    assert inbox.status_code == 200
    inbox_item = next(item for item in inbox.json() if item["event_id"] == event.id)
    assert set(inbox_item) == {
        "event_id",
        "event_title",
        "organization_name",
        "ends_at",
        "deletes_at",
        "status",
        "latest_at",
    }
    assert inbox_item["status"] == "archived"
    assert inbox_item["deletes_at"] == thread["deletes_at"]
    assert "retention sentinel message" not in json.dumps(inbox.json())
    deny(
        client.post(
            f"{API}/events/{event.id}/chat/messages",
            headers=auth(token_for(attendee)),
            json={"body": "too late", "client_key": str(uuid4())},
        )
    )

    event.ends_at = now() - timedelta(hours=72, seconds=1)
    event.starts_at = event.ends_at - timedelta(hours=2)
    db.commit()
    deny(client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(attendee))))
    expired_inbox = client.get(f"{API}/me/chats", headers=auth(token_for(attendee)))
    assert expired_inbox.status_code == 200
    assert all(item["event_id"] != event.id for item in expired_inbox.json())
    db.expire_all()
    assert db.get(ChatMessage, message_id) is not None  # Reads enforce cutoff; only the runner purges.


def test_report_role_isolation_and_personal_hide_and_resolution_are_scoped(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    moderator = make_user()
    add_org_role(db, organization, moderator, "moderator")
    other_owner = make_user()
    other_org = make_org(owner=other_owner)
    reporter = make_user()
    viewer = make_user()
    platform_admin = make_user(platform_admin=True)
    author = make_user(nickname="s7-subject-private-nickname")
    event = make_event(org=organization)

    created = comment(client, token_for, event, author, "visible report evidence")
    assert created.status_code < 300
    comment_id = created.json()["id"]
    content_report = report(client, token_for, event, reporter, "comment", comment_id, "harassment")
    assert content_report.status_code < 300
    receipt = content_report.json()
    assert receipt["stage"] == "organization"
    assert set(receipt) == REPORT_RECEIPT_KEYS

    for staff in (owner, moderator):
        listed = client.get(
            f"{API}/moderation/reports?org_id={organization.id}",
            headers=auth(token_for(staff)),
        )
        assert listed.status_code == 200
        assert receipt["id"] in {row["id"] for row in listed.json()}
    deny(
        client.get(
            f"{API}/moderation/reports?org_id={organization.id}",
            headers=auth(token_for(reporter)),
        )
    )
    deny(
        client.get(
            f"{API}/moderation/reports?org_id={organization.id}",
            headers=auth(token_for(other_owner)),
        )
    )
    own_other_org_reports = client.get(
        f"{API}/moderation/reports?org_id={other_org.id}",
        headers=auth(token_for(other_owner)),
    )
    assert own_other_org_reports.status_code == 200
    assert own_other_org_reports.json() == []
    deny(
        client.get(
            f"{API}/moderation/reports/{receipt['id']}",
            headers=auth(token_for(other_owner)),
        )
    )

    own_reports = client.get(f"{API}/me/reports", headers=auth(token_for(reporter)))
    assert own_reports.status_code == 200
    assert len(own_reports.json()) == 1
    assert set(own_reports.json()[0]) == REPORT_RECEIPT_KEYS
    assert "evidence" not in json.dumps(own_reports.json())
    assert client.get(f"{API}/me/reports", headers=auth(token_for(viewer))).json() == []

    public_before_hide = client.get(f"{API}/events/{event.id}/comments").json()["items"][0]
    assert public_before_hide["body"] == "visible report evidence"
    hidden = client.post(
        f"{API}/me/content-hides",
        headers=auth(token_for(reporter)),
        json={"event_id": event.id, "kind": "comment", "target_id": comment_id, "hidden": True},
    )
    assert hidden.status_code == 200
    assert hidden.json() == {"hidden": True}

    reporter_view = client.get(
        f"{API}/events/{event.id}/comments", headers=auth(token_for(reporter))
    ).json()["items"][0]
    viewer_view = client.get(
        f"{API}/events/{event.id}/comments", headers=auth(token_for(viewer))
    ).json()["items"][0]
    assert reporter_view["locally_hidden"] is True and reporter_view["body"] is None
    assert viewer_view["locally_hidden"] is False and viewer_view["body"] == "visible report evidence"
    duplicate_while_hidden = report(
        client, token_for, event, reporter, "comment", comment_id, "harassment"
    )
    assert duplicate_while_hidden.status_code < 300
    assert duplicate_while_hidden.json()["id"] == receipt["id"]

    restored = client.post(
        f"{API}/me/content-hides",
        headers=auth(token_for(reporter)),
        json={"event_id": event.id, "kind": "comment", "target_id": comment_id, "hidden": False},
    )
    assert restored.status_code == 200
    assert restored.json() == {"hidden": False}
    restored_view = client.get(
        f"{API}/events/{event.id}/comments", headers=auth(token_for(reporter))
    ).json()["items"][0]
    assert restored_view["body"] == "visible report evidence"

    tombstone = client.delete(
        f"{API}/events/{event.id}/comments/{comment_id}",
        headers=auth(token_for(author)),
    )
    assert tombstone.status_code < 300
    assert tombstone.json()["removed"] is True and tombstone.json()["body"] is None
    duplicate_after_removal = report(
        client, token_for, event, reporter, "comment", comment_id, "harassment"
    )
    assert duplicate_after_removal.status_code < 300
    assert duplicate_after_removal.json()["id"] == receipt["id"]
    retained = client.get(
        f"{API}/moderation/reports/{receipt['id']}", headers=auth(token_for(owner))
    )
    assert retained.status_code == 200
    assert retained.json()["evidence"] == "visible report evidence"

    dismissed = client.post(
        f"{API}/moderation/reports/{receipt['id']}/decision",
        headers=auth(token_for(owner)),
        json={"action": "dismiss"},
    )
    assert dismissed.status_code < 300
    closed = client.get(
        f"{API}/moderation/reports/{receipt['id']}", headers=auth(token_for(owner))
    )
    assert closed.status_code == 200
    assert closed.json()["evidence"] is None
    assert any(
        decision["action"] == "dismiss" and decision["reviewer_id"] == owner.id
        for decision in closed.json()["decisions"]
    )
    tombstones = client.get(f"{API}/events/{event.id}/comments").json()["items"]
    assert any(item["id"] == comment_id and item["removed"] and item["body"] is None for item in tombstones)

    person_basis = comment(client, token_for, event, author, "person identity visible")
    assert person_basis.status_code < 300
    person_report = report(client, token_for, event, reporter, "person", author.id, "impersonation")
    assert person_report.status_code < 300
    assert person_report.json()["stage"] == "platform"
    deny(
        client.get(
            f"{API}/moderation/reports/{person_report.json()['id']}",
            headers=auth(token_for(owner)),
        )
    )
    platform_detail = client.get(
        f"{API}/moderation/reports/{person_report.json()['id']}",
        headers=auth(token_for(platform_admin)),
    )
    assert platform_detail.status_code == 200
    assert platform_detail.json()["evidence"] == "person identity visible"


def test_pending_person_report_blocks_sending_without_revoking_read_reaction_or_seat(
    client, db, make_event, make_org, make_user, token_for
):
    from app.domains.events.models import Event

    event = make_event(org=make_org(), capacity=1)
    subject = make_user()
    reporter = make_user()
    subject_org = make_org(owner=subject)
    existing_draft = make_event(org=subject_org, status="draft", published_at=None)
    register(client, token_for, event, subject)
    subject_comment_key = str(uuid4())
    subject_comment_body = "visible person-report basis"
    subject_comment = comment(
        client, token_for, event, subject, subject_comment_body, subject_comment_key
    )
    assert subject_comment.status_code < 300
    message_key = str(uuid4())
    message_body = "existing chat remains readable"
    initial_message = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(subject)),
        json={"body": message_body, "client_key": message_key},
    )
    assert initial_message.status_code < 300

    personal = report(
        client,
        token_for,
        event,
        reporter,
        "person",
        subject.id,
        "deception",
    )
    assert personal.status_code < 300
    assert personal.json()["stage"] == "platform"
    assert report(
        client, token_for, event, subject, "person", subject.id, "other"
    ).status_code == 403

    blocked_draft = client.post(
        f"{API}/organizations/{subject_org.id}/events",
        headers=auth(token_for(subject)),
        json={},
    )
    assert blocked_draft.status_code == 403
    blocked_publish = client.post(
        f"{API}/events/{existing_draft.id}/publish",
        headers=auth(token_for(subject)),
    )
    assert blocked_publish.status_code == 403
    assert db.scalar(select(func.count()).select_from(Event).where(Event.org_id == subject_org.id)) == 1
    db.refresh(existing_draft)
    assert existing_draft.status == "draft"

    assert client.get(f"{API}/events/{event.id}/comments").status_code == 200
    thread = client.get(f"{API}/events/{event.id}/chat", headers=auth(token_for(subject)))
    assert thread.status_code == 200
    assert thread.json()["can_send"] is False
    assert any(item["id"] == initial_message.json()["id"] for item in thread.json()["items"])
    assert client.post(
        f"{API}/events/{event.id}/reactions",
        headers=auth(token_for(subject)),
        json={"reaction": "support"},
    ).status_code == 200

    comment_retry = comment(
        client, token_for, event, subject, subject_comment_body, subject_comment_key
    )
    assert comment_retry.status_code == 200
    assert comment_retry.json()["id"] == subject_comment.json()["id"]
    message_retry = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(subject)),
        json={"body": message_body, "client_key": message_key},
    )
    assert message_retry.status_code == 200
    assert message_retry.json()["id"] == initial_message.json()["id"]

    blocked_comment = comment(client, token_for, event, subject, "restricted new comment")
    assert blocked_comment.status_code == 403
    blocked_message = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(subject)),
        json={"body": "restricted new chat message", "client_key": str(uuid4())},
    )
    assert blocked_message.status_code == 403

    remaining_comments = client.get(f"{API}/events/{event.id}/comments").json()["items"]
    remaining_chat = client.get(
        f"{API}/events/{event.id}/chat", headers=auth(token_for(subject))
    ).json()["items"]
    assert [item["id"] for item in remaining_comments] == [subject_comment.json()["id"]]
    assert [item["id"] for item in remaining_chat] == [initial_message.json()["id"]]

    registrations = client.get(f"{API}/me/registrations", headers=auth(token_for(subject)))
    assert registrations.status_code == 200
    assert any(row["event_id"] == event.id and row["status"] == "confirmed" for row in registrations.json())
    db.expire_all()
    seat = db.scalar(
        select(Registration).where(
            Registration.event_id == event.id,
            Registration.user_id == subject.id,
        )
    )
    assert seat.status == "confirmed"
    projection = client.get(f"{API}/events/{event.id}").json()
    assert projection["confirmed_count"] == 1
    assert projection["reserved_count"] == 0
    assert projection["remaining_spots"] == 0


def test_report_and_chat_retention_survive_restart_then_expire_without_removing_comments(
    client, db, make_event, make_org, make_user, token_for
):
    from app.domains.chat.models import ChatMessage
    from app.domains.moderation.models import ContentHide, ContentReport, ReportDecision
    from app.domains.social.models import EventComment
    from app.notifications import Notification

    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization, capacity=2)
    author, reporter = make_user(), make_user()
    register(client, token_for, event, author)
    register(client, token_for, event, reporter)
    original_comment = comment(client, token_for, event, author, "retained comment snapshot")
    assert original_comment.status_code < 300
    original_message = client.post(
        f"{API}/events/{event.id}/chat/messages",
        headers=auth(token_for(author)),
        json={"body": "retained chat snapshot", "client_key": str(uuid4())},
    )
    assert original_message.status_code < 300
    comment_report = report(
        client, token_for, event, reporter, "comment", original_comment.json()["id"], "harassment"
    )
    message_report = report(
        client, token_for, event, reporter, "message", original_message.json()["id"], "spam"
    )
    assert comment_report.status_code < 300 and message_report.status_code < 300

    hidden = client.post(
        f"{API}/me/content-hides",
        headers=auth(token_for(reporter)),
        json={
            "event_id": event.id,
            "kind": "message",
            "target_id": original_message.json()["id"],
            "hidden": True,
        },
    )
    assert hidden.status_code == 200

    stored_deadline = now() - timedelta(days=1)
    report_ids = [comment_report.json()["id"], message_report.json()["id"]]
    for report_id in report_ids:
        db.get(ContentReport, report_id).deadline = stored_deadline
    event.starts_at = now() - timedelta(hours=75)
    event.ends_at = now() - timedelta(hours=73)
    db.commit()

    run_deadline_worker()
    db.expire_all()
    chat_row = db.get(ChatMessage, original_message.json()["id"])
    assert chat_row is None
    assert db.scalar(
        select(func.count()).select_from(ContentHide).where(
            ContentHide.user_id == reporter.id,
            ContentHide.kind == "message",
            ContentHide.target_id == original_message.json()["id"],
        )
    ) == 0
    for report_id in report_ids:
        current = db.get(ContentReport, report_id)
        assert current.status == "escalated"
        assert current.stage == "platform"
        assert current.deadline == stored_deadline + timedelta(days=14)
        assert current.evidence in {"retained comment snapshot", "retained chat snapshot"}
    assert db.scalar(
        select(func.count()).select_from(ReportDecision).where(
            ReportDecision.report_id.in_(report_ids),
            ReportDecision.action == "escalate",
        )
    ) == 2

    platform_admin = make_user(platform_admin=True)
    retained_detail = client.get(
        f"{API}/moderation/reports/{message_report.json()['id']}",
        headers=auth(token_for(platform_admin)),
    )
    assert retained_detail.status_code == 200
    assert retained_detail.json()["evidence"] == "retained chat snapshot"
    deny(
        client.get(
            f"{API}/events/{event.id}/chat", headers=auth(token_for(reporter))
        )
    )
    assert client.get(f"{API}/events/{event.id}/comments").json()["items"][0]["body"] == "retained comment snapshot"

    notices = list(db.scalars(select(Notification).where(Notification.event_id == event.id)))
    first_keys = {notice.dedupe_key for notice in notices}
    assert len(first_keys) == len(notices)
    for notice in notices:
        rendered = json.dumps(
            {"kind": notice.kind, "message": notice.message, "dedupe_key": notice.dedupe_key},
            ensure_ascii=False,
        ).lower()
        assert "retained comment snapshot" not in rendered
        assert "retained chat snapshot" not in rendered
        assert "harassment" not in rendered and "spam" not in rendered
        assert author.email.lower() not in rendered and reporter.email.lower() not in rendered

    run_deadline_worker()  # A new process must not duplicate the escalations or notices.
    db.expire_all()
    assert {notice.dedupe_key for notice in db.scalars(select(Notification).where(Notification.event_id == event.id))} == first_keys
    assert db.scalar(
        select(func.count()).select_from(ReportDecision).where(
            ReportDecision.report_id.in_(report_ids),
            ReportDecision.action == "escalate",
        )
    ) == 2

    for report_id in report_ids:
        db.get(ContentReport, report_id).deadline = now() - timedelta(seconds=1)
    db.commit()
    run_deadline_worker()
    db.expire_all()
    for report_id in report_ids:
        expired = db.get(ContentReport, report_id)
        assert expired.status == "expired"
        assert expired.resolved_at is not None
        assert expired.evidence is None
    assert db.scalar(
        select(func.count()).select_from(ReportDecision).where(
            ReportDecision.report_id.in_(report_ids),
            ReportDecision.action == "expire",
        )
    ) == 2
    comment_row = db.get(EventComment, original_comment.json()["id"])
    assert comment_row.removed_at is None
    assert comment_row.body == "retained comment snapshot"

    final_keys = {notice.dedupe_key for notice in db.scalars(select(Notification).where(Notification.event_id == event.id))}
    assert len(final_keys) == len(
        list(db.scalars(select(Notification).where(Notification.event_id == event.id)))
    )
    run_deadline_worker()
    db.expire_all()
    assert {notice.dedupe_key for notice in db.scalars(select(Notification).where(Notification.event_id == event.id))} == final_keys


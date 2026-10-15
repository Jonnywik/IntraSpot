from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.communication_schemas import ContentCreate
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.moderation.models import ContentHide, ContentReport
from app.domains.organizations.models import Organization  # noqa: F401 - register event/report foreign-key targets before fixture cleanup
from app.domains.social import service
from app.domains.social.models import EventComment, EventReaction


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def comment_payload(body, key=None):
    return {"body": body, "client_key": str(key or uuid4())}


def test_guest_reads_published_content_but_never_draft_or_private_profile_fields(
    client, db, make_user, make_event, token_for
):
    author = make_user(nickname="Private fictional nickname", persona_visible=False)
    event = make_event()
    draft = make_event(status="draft", published_at=None)
    posted = client.post(
        f"/api/v1/events/{event.id}/comments",
        json=comment_payload("Visible comment"),
        headers=auth(token_for(author)),
    )
    assert posted.status_code == 200

    reactions = client.get(f"/api/v1/events/{event.id}/reactions")
    comments = client.get(f"/api/v1/events/{event.id}/comments")
    assert reactions.status_code == comments.status_code == 200
    assert reactions.json()["can_react"] is False
    item = comments.json()["items"][0]
    assert item["body"] == "Visible comment"
    assert item["author_label"] == "PLM member"
    assert item["author_id"] == author.id
    assert item["removed"] is False
    assert item["locally_hidden"] is False
    assert "Private fictional nickname" not in comments.text
    assert author.email not in comments.text
    assert set(item) == {
        "id", "event_id", "author_id", "author_label", "sequence", "body",
        "created_at", "removed", "locally_hidden", "mine",
    }

    assert client.get(f"/api/v1/events/{draft.id}/reactions").status_code == 404
    assert client.get(f"/api/v1/events/{draft.id}/comments").status_code == 404
    assert client.post(
        f"/api/v1/events/{draft.id}/reactions",
        json={"reaction": "interested"},
        headers=auth(token_for(author)),
    ).status_code == 404
    assert db.scalar(select(func.count(EventComment.id)).where(EventComment.event_id == draft.id)) == 0


def test_guests_and_ineligible_users_cannot_write(client, make_user, make_event, token_for):
    event = make_event()
    assert client.post(
        f"/api/v1/events/{event.id}/reactions", json={"reaction": "interested"}
    ).status_code == 401
    assert client.post(
        f"/api/v1/events/{event.id}/comments", json=comment_payload("Guest")
    ).status_code == 401

    outside_user = make_user(email="fictional-outside@example.test")
    headers = auth(token_for(outside_user))
    reaction = client.post(
        f"/api/v1/events/{event.id}/reactions",
        json={"reaction": "interested"},
        headers=headers,
    )
    comment = client.post(
        f"/api/v1/events/{event.id}/comments",
        json=comment_payload("Not eligible"),
        headers=headers,
    )
    assert reaction.status_code == comment.status_code == 403
    assert reaction.json()["error"]["code"] == "plm_email_required"
    assert comment.json()["error"]["code"] == "plm_email_required"


def test_desired_reactions_are_idempotent_and_adjust_interest_delta_only(
    client, db, make_user, make_event, token_for
):
    user = make_user()
    event = make_event(interest_count=9)
    headers = auth(token_for(user))
    url = f"/api/v1/events/{event.id}/reactions"

    interested = client.post(url, json={"reaction": "interested"}, headers=headers)
    assert interested.status_code == 200
    assert interested.json()["counts"] == {
        "interested": 1, "excited": 0, "support": 0,
        "kudos": 0, "wow": 0, "relate": 0,
    }
    assert interested.json()["mine"] == "interested"
    assert client.post(url, json={"reaction": "interested"}, headers=headers).json()["total"] == 1
    assert db.scalar(select(Event.interest_count).where(Event.id == event.id)) == 10

    changed = client.post(url, json={"reaction": "excited"}, headers=headers)
    assert changed.json()["mine"] == "excited"
    assert changed.json()["counts"]["interested"] == 0
    assert changed.json()["counts"]["excited"] == 1
    assert db.scalar(select(Event.interest_count).where(Event.id == event.id)) == 9

    cleared = client.post(url, json={"reaction": None}, headers=headers)
    assert cleared.json()["total"] == 0
    assert cleared.json()["mine"] is None
    assert db.scalar(select(Event.interest_count).where(Event.id == event.id)) == 9
    assert db.scalar(select(func.count(EventReaction.id)).where(EventReaction.event_id == event.id)) == 0


def test_pending_person_report_blocks_comment_send_but_not_reactions(
    client, db, make_user, make_event, token_for
):
    subject = make_user()
    reporter = make_user()
    event = make_event()
    db.add(
        ContentReport(
            id=uid(),
            event_id=event.id,
            org_id=event.org_id,
            reporter_id=reporter.id,
            subject_user_id=subject.id,
            kind="person",
            target_id=subject.id,
            reason="other",
            status="open",
            stage="platform",
            deadline=now() + timedelta(days=2),
        )
    )
    db.commit()
    headers = auth(token_for(subject))

    reaction = client.post(
        f"/api/v1/events/{event.id}/reactions",
        json={"reaction": "interested"},
        headers=headers,
    )
    comment = client.post(
        f"/api/v1/events/{event.id}/comments",
        json=comment_payload("Blocked while personal review is pending"),
        headers=headers,
    )
    assert reaction.status_code == 200
    assert reaction.json()["mine"] == "interested"
    assert comment.status_code == 403
    assert comment.json()["error"]["code"] == "personal_review_pending"
    assert db.scalar(select(func.count(EventComment.id)).where(EventComment.event_id == event.id)) == 0


def test_comment_idempotency_and_sequence_pagination_are_stable(
    client, db, make_user, make_event, token_for
):
    author = make_user()
    event = make_event()
    headers = auth(token_for(author))
    url = f"/api/v1/events/{event.id}/comments"
    keys = [uuid4() for _ in range(3)]
    created = [
        client.post(url, json=comment_payload(f"Comment {index}", keys[index]), headers=headers)
        for index in range(3)
    ]
    assert all(response.status_code == 200 for response in created)

    retry = client.post(url, json=comment_payload("Comment 0", keys[0]), headers=headers)
    conflict = client.post(url, json=comment_payload("Different body", keys[0]), headers=headers)
    assert retry.status_code == 200
    assert retry.json()["id"] == created[0].json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert db.scalar(select(func.count(EventComment.id)).where(EventComment.event_id == event.id)) == 3

    first_page = client.get(url, params={"limit": 2})
    assert [item["body"] for item in first_page.json()["items"]] == ["Comment 2", "Comment 1"]
    assert first_page.json()["next_before"] == first_page.json()["items"][-1]["sequence"]
    second_page = client.get(
        url,
        params={"limit": 2, "before_sequence": first_page.json()["next_before"]},
    )
    assert [item["body"] for item in second_page.json()["items"]] == ["Comment 0"]
    assert second_page.json()["next_before"] is None


def test_event_start_is_an_inclusive_mutation_boundary(db, make_user, make_event):
    user = make_user()
    event = make_event()

    with pytest.raises(DomainError) as reaction_error:
        service.set_reaction(db, event.id, user.id, "interested", at=event.starts_at)
    assert reaction_error.value.code == "event_started"

    with pytest.raises(DomainError) as create_error:
        service.create_comment(
            db,
            event.id,
            user.id,
            ContentCreate(body="At the boundary", client_key=uuid4()),
            at=event.starts_at,
        )
    assert create_error.value.code == "event_started"

    comment = service.create_comment(
        db,
        event.id,
        user.id,
        ContentCreate(body="Before the boundary", client_key=uuid4()),
        at=now(),
    )
    with pytest.raises(DomainError) as delete_error:
        service.delete_comment(db, event.id, comment.id, user.id, at=event.starts_at)
    assert delete_error.value.code == "event_started"


def test_local_hide_is_private_and_deletion_tombstones_without_erasing_report_evidence(
    client, db, make_user, make_event, token_for
):
    author = make_user(nickname="Private author", persona_visible=False)
    viewer = make_user()
    reporter = make_user()
    event = make_event()
    headers = auth(token_for(author))
    posted = client.post(
        f"/api/v1/events/{event.id}/comments",
        json=comment_payload("Retained reported evidence"),
        headers=headers,
    )
    assert posted.status_code == 200
    comment_id = posted.json()["id"]
    evidence_text = "Evidence retained for authorized review"
    report = ContentReport(
        id=uid(),
        event_id=event.id,
        org_id=event.org_id,
        reporter_id=reporter.id,
        subject_user_id=author.id,
        kind="comment",
        target_id=comment_id,
        reason="other",
        status="open",
        stage="organization",
        evidence=evidence_text,
        deadline=now() + timedelta(days=2),
    )
    db.add(report)
    db.add(
        ContentHide(
            id=uid(),
            user_id=viewer.id,
            event_id=event.id,
            kind="comment",
            target_id=comment_id,
        )
    )
    db.commit()

    hidden = client.get(
        f"/api/v1/events/{event.id}/comments", headers=auth(token_for(viewer))
    ).json()["items"][0]
    visible = client.get(f"/api/v1/events/{event.id}/comments").json()["items"][0]
    assert hidden["body"] is None
    assert hidden["locally_hidden"] is True
    assert visible["body"] == "Retained reported evidence"
    assert visible["locally_hidden"] is False

    deleted = client.delete(
        f"/api/v1/events/{event.id}/comments/{comment_id}", headers=headers
    )
    assert deleted.status_code == 200
    assert deleted.json()["body"] is None
    assert deleted.json()["removed"] is True
    assert db.get(EventComment, comment_id).body is None
    assert db.get(ContentReport, report.id).evidence == evidence_text

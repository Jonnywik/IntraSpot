"""Serial PostgreSQL quality coverage for the frozen Sprint 6 contract."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.db.models import now, uid
from app.domains.events.models import Event
from app.domains.organizations.models import OrgMembership
from app.domains.registrations import service
from app.domains.registrations.models import Registration, RegistrationReceipt


API = "/api/v1"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKER_TIMEOUT_SECONDS = 30
REDACTED_REVIEW_KEYS = {
    "email",
    "image",
    "image_key",
    "image_url",
    "profile_image",
    "profile_image_key",
    "profile_image_url",
    "avatar_url",
}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_approval_event(make_event, organization, *, capacity):
    return make_event(
        org=organization,
        capacity=capacity,
        registration_mode="approval",
        review_window_minutes=15,
    )


def run_together(actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = {name: pool.submit(run, action) for name, action in actions.items()}
        return {name: future.result(timeout=30) for name, future in futures.items()}


def add_org_role(db, organization, user, role):
    db.add(
        OrgMembership(
            id=uid(),
            org_id=organization.id,
            user_id=user.id,
            role=role,
            active=True,
        )
    )
    db.commit()


def register(client, token_for, event, user, key, *, persona_shared=False):
    response = client.post(
        f"{API}/events/{event.id}/registrations",
        headers=auth(token_for(user)) | {"Idempotency-Key": key},
        json={"persona_shared": persona_shared},
    )
    assert response.status_code < 300
    return response.json()


def decide(client, token_for, event, registration_id, reviewer, decision):
    response = client.post(
        f"{API}/events/{event.id}/registrations/{registration_id}/decision",
        headers=auth(token_for(reviewer)),
        json={"decision": decision},
    )
    assert response.status_code < 300
    return response.json()


def change_event(client, token_for, event, owner, **fields):
    payload = {
        "reconfirm_deadline": (now() + timedelta(days=1)).isoformat(),
        **fields,
    }
    return client.post(
        f"{API}/events/{event.id}/changes",
        headers=auth(token_for(owner)),
        json=payload,
    )


def registration_statuses(db, registration_ids):
    db.expire_all()
    rows = db.scalars(
        select(Registration).where(Registration.id.in_(registration_ids))
    ).all()
    return {row.id: row.status for row in rows}


def nested_keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(item) for item in value)) if value else set()
    return set()


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


def test_cross_org_moderator_cannot_read_or_decide_on_registration(
    client, db, make_event, make_org, make_user, token_for
):
    from app.notifications import Notification

    owner = make_user()
    organization = make_org(owner=owner)
    event = make_approval_event(make_event, organization, capacity=1)
    foreign_owner = make_user()
    foreign_org = make_org(owner=foreign_owner)
    foreign_moderator = make_user()
    add_org_role(db, foreign_org, foreign_moderator, "moderator")
    applicant = make_user(nickname="private-cross-org-persona")
    created = register(client, token_for, event, applicant, "s6-cross-org-01", persona_shared=True)
    registration = db.get(Registration, created["id"])
    registration.review_deadline = now() - timedelta(minutes=1)
    registration.review_stage = 0
    db.commit()

    def review_state():
        db.expire_all()
        current = db.get(Registration, created["id"])
        notice_keys = tuple(
            sorted(
                db.scalars(
                    select(Notification.dedupe_key).where(
                        Notification.event_id == event.id,
                        Notification.registration_id == created["id"],
                    )
                )
            )
        )
        return (
            current.status,
            current.review_deadline,
            current.review_stage,
            current.timeout_count,
            notice_keys,
        )

    before = review_state()

    headers = auth(token_for(foreign_moderator))
    queue = client.get(f"{API}/events/{event.id}/registration-review", headers=headers)
    assert queue.status_code == 403
    assert review_state() == before

    decision = client.post(
        f"{API}/events/{event.id}/registrations/{created['id']}/decision",
        headers=headers,
        json={"decision": "reject"},
    )

    assert decision.status_code == 403
    assert review_state() == before
    assert applicant.nickname not in queue.text
    assert applicant.email not in queue.text
    assert applicant.nickname not in decision.text
    assert applicant.email not in decision.text


def test_reviewer_projection_obeys_event_opt_in_and_omits_email_and_images(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    moderator = make_user()
    add_org_role(db, organization, moderator, "moderator")
    event = make_approval_event(make_event, organization, capacity=2)
    opted_in = make_user(
        nickname="review-visible-nickname",
        age_bracket="review-visible-age",
        tags=["review-visible-tag"],
        pronouns="review-visible-pronouns",
        icebreaker="review-visible-icebreaker",
    )
    not_opted_in = make_user(
        nickname="review-hidden-nickname",
        age_bracket="review-hidden-age",
        tags=["review-hidden-tag"],
        pronouns="review-hidden-pronouns",
        icebreaker="review-hidden-icebreaker",
        persona_visible=True,
    )
    visible = register(client, token_for, event, opted_in, "s6-review-optin-01", persona_shared=True)
    hidden = register(client, token_for, event, not_opted_in, "s6-review-optout-01")

    response = client.get(
        f"{API}/events/{event.id}/registration-review",
        headers=auth(token_for(moderator)),
    )
    assert response.status_code == 200
    rows = {row["registration"]["id"]: row for row in response.json()}
    assert visible["id"] in rows and hidden["id"] in rows
    assert all(row["registration"]["review_stage"] == 0 for row in rows.values())
    assert all(type(row["registration"]["review_stage"]) is int for row in rows.values())

    serialized = json.dumps(response.json(), ensure_ascii=False)
    for allowed in (
        opted_in.nickname,
        opted_in.age_bracket,
        opted_in.tags[0],
        opted_in.pronouns,
        opted_in.icebreaker,
    ):
        assert allowed in serialized
    for private in (
        not_opted_in.nickname,
        not_opted_in.age_bracket,
        not_opted_in.tags[0],
        not_opted_in.pronouns,
        not_opted_in.icebreaker,
        opted_in.email,
        not_opted_in.email,
    ):
        assert private not in serialized
    assert {key.lower() for key in nested_keys(response.json())}.isdisjoint(REDACTED_REVIEW_KEYS)


def test_capacity_reduction_defaults_to_exact_and_preserves_unselected_holders(
    client, db, make_event, make_org, make_user, token_for
):
    from app.notifications import Notification

    owner = make_user()
    organization = make_org(owner=owner)
    org_member = make_user()
    add_org_role(db, organization, org_member, "member")
    event = make_approval_event(make_event, organization, capacity=4)
    attendees = [make_user() for _ in range(4)]
    created = [
        register(client, token_for, event, attendee, f"s6-exact-{index:02d}")
        for index, attendee in enumerate(attendees)
    ]
    assert [row["status"] for row in created] == ["pending"] * 4
    for row in created[:3]:
        decide(client, token_for, event, row["id"], owner, "approve")

    selected = [created[0]["id"], created[1]["id"]]
    response = change_event(
        client,
        token_for,
        event,
        owner,
        capacity=2,
        selected_registration_ids=selected,
    )

    assert response.status_code < 300
    statuses = registration_statuses(db, [row["id"] for row in created])
    assert statuses[selected[0]] == statuses[selected[1]] == "cancelled"
    assert statuses[created[2]["id"]] == "reconfirmation_required"
    assert statuses[created[3]["id"]] == "pending"
    projection = client.get(f"{API}/events/{event.id}").json()
    assert projection["confirmed_count"] == 0
    assert projection["reserved_count"] == 2
    assert projection["remaining_spots"] == 0
    db.refresh(event)
    assert event.material_revision == 1
    member_notices = list(
        db.scalars(
            select(Notification).where(
                Notification.event_id == event.id,
                Notification.user_id.in_([owner.id, org_member.id]),
                Notification.kind == "event_material_change",
                Notification.registration_id.is_(None),
            )
        )
    )
    assert {notice.user_id for notice in member_notices} == {owner.id, org_member.id}
    assert len(member_notices) == 2


def test_newest_in_pool_cancels_only_the_newest_submitted_candidates(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_approval_event(make_event, organization, capacity=4)
    attendees = [make_user() for _ in range(4)]
    created = [
        register(client, token_for, event, attendee, f"s6-pool-{index:02d}")
        for index, attendee in enumerate(attendees)
    ]
    for row in created:
        decide(client, token_for, event, row["id"], owner, "approve")

    db.expire_all()
    base = now() - timedelta(minutes=4)
    confirmed_at_by_index = {
        0: base,
        1: base + timedelta(minutes=3),
        2: base + timedelta(minutes=3),
        3: base + timedelta(minutes=1),
    }
    for index, row in enumerate(created):
        registration = db.get(Registration, row["id"])
        registration.confirmed_at = confirmed_at_by_index[index]
    db.commit()
    pool = [created[index]["id"] for index in (1, 2, 3)]

    response = change_event(
        client,
        token_for,
        event,
        owner,
        capacity=2,
        selection_mode="newest_in_pool",
        selected_registration_ids=pool,
    )

    assert response.status_code < 300
    statuses = registration_statuses(db, [row["id"] for row in created])
    assert statuses[created[0]["id"]] == "reconfirmation_required"  # outside the submitted pool
    assert statuses[created[1]["id"]] == statuses[created[2]["id"]] == "cancelled"
    assert statuses[created[3]["id"]] == "reconfirmation_required"  # older unselected pool member


def test_newest_in_pool_rejects_nonempty_selection_without_a_capacity_deficit(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_approval_event(make_event, organization, capacity=1)
    attendee = make_user()
    created = register(client, token_for, event, attendee, "s6-pool-no-deficit-01")
    assert created["status"] == "pending"

    response = change_event(
        client,
        token_for,
        event,
        owner,
        capacity=2,
        venue_name="A larger fictional courtyard",
        selection_mode="newest_in_pool",
        selected_registration_ids=[created["id"]],
    )

    assert response.status_code == 422
    db.expire_all()
    current_event = db.get(Event, event.id)
    current_registration = db.get(Registration, created["id"])
    assert current_event.capacity == 1
    assert current_event.material_revision == 0
    assert current_registration.status == "pending"
    assert current_registration.reconfirm_revision is None


def test_pending_and_reconfirmation_reservations_both_block_capacity(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_approval_event(make_event, organization, capacity=2)
    attendees = [make_user() for _ in range(5)]
    created = [
        register(client, token_for, event, attendee, f"s6-reserve-{index:02d}")
        for index, attendee in enumerate(attendees[:3])
    ]
    assert [row["status"] for row in created] == ["pending", "pending", "waitlisted"]
    decide(client, token_for, event, created[0]["id"], owner, "approve")

    fourth = register(client, token_for, event, attendees[3], "s6-reserve-03")
    assert fourth["status"] == "waitlisted"
    before = client.get(f"{API}/events/{event.id}").json()
    assert before["confirmed_count"] == 1
    assert before["reserved_count"] == 1
    assert before["remaining_spots"] == 0

    changed = change_event(
        client,
        token_for,
        event,
        owner,
        venue_name="Updated fictional courtyard",
    )
    assert changed.status_code < 300
    fifth = register(client, token_for, event, attendees[4], "s6-reserve-04")
    assert fifth["status"] == "waitlisted"

    after = client.get(f"{API}/events/{event.id}").json()
    assert after["confirmed_count"] == 0
    assert after["reserved_count"] == 2
    assert after["remaining_spots"] == 0
    statuses = registration_statuses(db, [created[0]["id"], created[1]["id"]])
    assert statuses[created[0]["id"]] == "reconfirmation_required"
    assert statuses[created[1]["id"]] == "pending"


def test_ten_concurrent_approval_submissions_reserve_only_three_seats(
    db, make_event, make_org, make_user
):
    organization = make_org()
    event = make_approval_event(make_event, organization, capacity=3)
    applicants = [make_user() for _ in range(10)]

    outcomes = run_together(
        {
            f"applicant-{index}": lambda applicant=applicant, index=index: service.submit_registration(
                applicant.id, event.id, f"s6-concurrent-{index:02d}"
            )
            for index, applicant in enumerate(applicants)
        }
    )

    statuses = [outcome.result["status"] for outcome in outcomes.values()]
    assert statuses.count("pending") == 3
    assert statuses.count("waitlisted") == 7
    pending_stages = [
        outcome.result["review_stage"]
        for outcome in outcomes.values()
        if outcome.result["status"] == "pending"
    ]
    assert pending_stages == [0] * 3
    assert all(type(stage) is int for stage in pending_stages)

    db.expire_all()
    event = db.get(Event, event.id)
    registrations = list(
        db.scalars(select(Registration).where(Registration.event_id == event.id))
    )
    receipts = list(
        db.scalars(
            select(RegistrationReceipt).where(RegistrationReceipt.event_id == event.id)
        )
    )
    assert len(registrations) == 10
    assert sum(registration.status == "pending" for registration in registrations) == 3
    assert sum(registration.status == "waitlisted" for registration in registrations) == 7
    assert len(receipts) == 10
    assert len({receipt.event_order for receipt in receipts}) == 10
    assert event.next_admission == 10


def test_stale_reconfirmation_revision_cannot_release_the_current_reservation(
    client, db, make_event, make_org, make_user, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization, capacity=2)
    attendee = make_user()
    created = register(client, token_for, event, attendee, "s6-reconfirm-01")
    assert created["status"] == "confirmed"

    first_change = change_event(
        client,
        token_for,
        event,
        owner,
        venue_name="First fictional venue",
    )
    assert first_change.status_code < 300
    first_revision = client.get(f"{API}/events/{event.id}").json()["material_revision"]
    second_change = change_event(
        client,
        token_for,
        event,
        owner,
        cost_label="Updated fictional cost",
    )
    assert second_change.status_code < 300
    current_revision = client.get(f"{API}/events/{event.id}").json()["material_revision"]
    assert current_revision == first_revision + 1

    stale = client.post(
        f"{API}/events/{event.id}/registrations/me/reconfirmation",
        headers=auth(token_for(attendee)),
        json={"accept": True, "revision": first_revision},
    )
    assert stale.status_code >= 400
    assert registration_statuses(db, [created["id"]])[created["id"]] == "reconfirmation_required"

    current = client.post(
        f"{API}/events/{event.id}/registrations/me/reconfirmation",
        headers=auth(token_for(attendee)),
        json={"accept": True, "revision": current_revision},
    )
    assert current.status_code < 300
    assert current.json()["status"] == "confirmed"


def test_deadline_escalation_is_restart_safe_deduped_and_excludes_first_reviewer(
    client, db, make_event, make_org, make_user, token_for
):
    from app.notifications import Notification

    owner = make_user()
    organization = make_org(owner=owner)
    second_reviewer = make_user()
    add_org_role(db, organization, second_reviewer, "admin")
    event = make_approval_event(make_event, organization, capacity=1)
    applicant = make_user()
    created = register(client, token_for, event, applicant, "s6-deadline-01")

    db.expire_all()
    registration = db.get(Registration, created["id"])
    initial_deadline = now() - timedelta(minutes=1)
    registration.review_deadline = initial_deadline
    db.commit()

    run_deadline_worker()
    db.expire_all()
    registration = db.get(Registration, created["id"])
    assert registration.status == "pending"
    assert registration.review_stage == 1
    assert type(registration.review_stage) is int
    assert registration.review_deadline == initial_deadline + timedelta(minutes=15)
    warnings = list(db.scalars(select(Notification).where(
        Notification.registration_id == registration.id,
        Notification.kind == 'registration_review_warning',
    )))
    assert {notice.user_id for notice in warnings} == {applicant.id, owner.id}
    assert len(warnings) == 2
    extension_deadline = now() - timedelta(minutes=1)
    registration.review_deadline = extension_deadline
    db.commit()

    run_deadline_worker()
    db.expire_all()
    registration = db.get(Registration, created["id"])
    assert registration.status == "pending"
    assert registration.review_stage == 2
    assert type(registration.review_stage) is int
    assert registration.first_reviewer_id == owner.id
    assert registration.reviewer_id == second_reviewer.id
    assert registration.review_deadline == extension_deadline + timedelta(minutes=15)

    notices = list(
        db.scalars(
            select(Notification).where(
                Notification.event_id == event.id,
                Notification.registration_id == registration.id,
            )
        )
    )
    first_keys = {notice.dedupe_key for notice in notices}
    assert first_keys
    run_deadline_worker()
    db.expire_all()
    repeated_keys = {
        notice.dedupe_key
        for notice in db.scalars(
            select(Notification).where(
                Notification.event_id == event.id,
                Notification.registration_id == registration.id,
            )
        )
    }
    assert repeated_keys == first_keys

    initial_reviewer_decision = client.post(
        f"{API}/events/{event.id}/registrations/{registration.id}/decision",
        headers=auth(token_for(owner)),
        json={"decision": "approve"},
    )
    assert initial_reviewer_decision.status_code >= 400
    assert registration_statuses(db, [registration.id])[registration.id] == "pending"

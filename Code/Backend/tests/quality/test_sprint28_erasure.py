"""Sprint 28 account-erasure safety on isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from sqlalchemy import create_engine as sqlalchemy_create_engine, func, select

from app import account_erasure
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now, uid
from app.db.session import engine
from app.domains.chat.models import ChatMessage
from app.domains.events.models import Event
from app.domains.identity.discovery_models import UserDiscoveryPreferences
from app.domains.identity.models import User
from app.domains.identity.preferences_models import UserPreferences
from app.domains.identity import supabase_auth
from app.domains.moderation.models import ContentReport
from app.domains.organizations.models import OrgMembership
from app.domains.planning.models import SavedEvent
from app.domains.registrations.models import Registration
from app.domains.social.models import EventComment, EventReaction
from app.erasure_models import ErasedAccount, ErasureRequest
from app.notifications import Notification


@pytest.fixture(autouse=True)
def fixture_auth(monkeypatch):
    monkeypatch.setattr(account_erasure, "get_settings", lambda: SimpleNamespace(auth_provider="fixture"))


def _actor(user):
    return Actor(
        user_id=user.id,
        nickname=user.nickname,
        eligible=True,
        profile_complete=True,
        platform_admin=user.platform_admin,
    )


def _due_receipt(db, user):
    receipt = account_erasure.request_erasure(db, _actor(user))
    receipt.due_at = now() - timedelta(seconds=1)
    db.commit()
    return receipt.id


def test_request_receipt_is_idempotent_and_targets_thirty_days(db, make_user):
    user = make_user()

    first = account_erasure.request_erasure(db, _actor(user))
    second = account_erasure.request_erasure(db, _actor(user))

    assert first.id == second.id
    assert first.requested_at + timedelta(days=30) == first.due_at
    assert first.id != user.id
    assert account_erasure._receipt_result(first)["counts"] == {}
    assert "user_id" not in account_erasure._receipt_result(first)
    assert db.get(ErasureRequest, first.id).user_id == user.id


def test_pending_request_can_be_fulfilled_before_its_target_date(db, make_user):
    user = make_user()
    receipt = account_erasure.request_erasure(db, _actor(user))
    receipt_id = receipt.id
    due_at = receipt.due_at
    assert due_at > now()
    db.commit()

    result = account_erasure.fulfill_erasure(receipt_id)

    assert result["status"] == "completed"
    assert result["completed_at"] < due_at


def test_owner_must_transfer_before_erasure(db, make_user, make_org):
    owner = make_user()
    successor = make_user()
    org = make_org(owner=owner)
    owner_membership = db.scalar(
        select(OrgMembership).where(OrgMembership.org_id == org.id, OrgMembership.user_id == owner.id)
    )
    successor_membership = OrgMembership(
        id=uid(), org_id=org.id, user_id=successor.id, role="member", active=True
    )
    db.add(successor_membership)
    db.commit()

    receipt = account_erasure.request_erasure(db, _actor(owner))
    assert receipt.status == "blocked"
    assert receipt.blocker_code == "owner_transfer_required"
    receipt.due_at = now() - timedelta(seconds=1)
    db.commit()

    owner_membership.role = "member"
    db.flush()  # Release the unique active-owner slot before assigning its successor.
    successor_membership.role = "owner"
    db.commit()
    updated = account_erasure.request_erasure(db, _actor(owner))
    assert updated.id == receipt.id
    assert updated.status == "pending"
    db.commit()

    result = account_erasure.fulfill_erasure(receipt.id)

    assert result["status"] == "completed"
    assert result["counts"]["memberships_deactivated"] == 1


def test_concurrent_admin_erasures_leave_one_active_admin(db, make_user):
    admins = [make_user(platform_admin=True), make_user(platform_admin=True)]
    receipt_ids = [_due_receipt(db, user) for user in admins]
    start = Barrier(2)

    def fulfill(receipt_id):
        start.wait(timeout=5)
        return account_erasure.fulfill_erasure(receipt_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fulfill, receipt_ids))

    assert sorted(result["status"] for result in results) == ["blocked", "completed"]
    blocked = next(result for result in results if result["status"] == "blocked")
    assert blocked["blocker_code"] == "platform_admin_replacement_required"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User).where(
        User.active.is_(True), User.platform_admin.is_(True)
    )) == 1


def test_fulfillment_scrubs_private_data_and_preserves_history_and_report_evidence(
    db, make_user, make_org, make_event
):
    owner = make_user()
    user = make_user()
    waiter = make_user()
    org = make_org(owner=owner)
    membership = OrgMembership(id=uid(), org_id=org.id, user_id=user.id, role="member", active=True)
    future_start = now() + timedelta(days=3)
    future_event = make_event(
        org=org, capacity=1, starts_at=future_start, ends_at=future_start + timedelta(hours=2)
    )
    past_event = make_event(
        org=org,
        starts_at=now() - timedelta(days=2),
        ends_at=now() - timedelta(days=2) + timedelta(hours=2),
    )
    future_registration = Registration(
        id=uid(), user_id=user.id, event_id=future_event.id, status="confirmed",
        admission_order=1, persona_shared=True,
    )
    waiter_registration = Registration(
        id=uid(), user_id=waiter.id, event_id=future_event.id, status="waitlisted", admission_order=2,
    )
    past_registration = Registration(
        id=uid(), user_id=user.id, event_id=past_event.id, status="confirmed",
        admission_order=1, persona_shared=True,
    )
    future_event.interest_count = 1
    reaction = EventReaction(
        id=uid(), event_id=future_event.id, user_id=user.id, kind="interested",
    )
    saved = SavedEvent(user_id=user.id, event_id=future_event.id)
    preferences = UserPreferences(user_id=user.id)
    discovery = UserDiscoveryPreferences(user_id=user.id)
    notice = Notification(
        id=uid(), user_id=user.id, event_id=future_event.id, org_id=org.id,
        kind="event_material_change", message="Private notice", dedupe_key=f"private:{uid()}",
    )
    notice_id = notice.id
    held_comment = EventComment(
        id=uid(), event_id=future_event.id, author_id=user.id, body="reported comment",
        body_hash="a" * 64, client_key="comment-held",
    )
    scrubbed_comment = EventComment(
        id=uid(), event_id=future_event.id, author_id=user.id, body="private comment",
        body_hash="b" * 64, client_key="comment-private",
    )
    held_message = ChatMessage(
        id=uid(), event_id=future_event.id, author_id=user.id, body="reported message",
        body_hash="c" * 64, client_key="message-held",
    )
    scrubbed_message = ChatMessage(
        id=uid(), event_id=future_event.id, author_id=user.id, body="private message",
        body_hash="d" * 64, client_key="message-private",
    )
    deadline = now() + timedelta(days=2)
    reports = [
        ContentReport(
            id=uid(), event_id=future_event.id, org_id=org.id, reporter_id=owner.id,
            subject_user_id=user.id, kind=kind, target_id=target.id, reason="other",
            status="open", stage="organization", deadline=deadline,
            evidence=f"report snapshot {kind}",
        )
        for kind, target in (("comment", held_comment), ("message", held_message))
    ]
    report_ids = {report.kind: report.id for report in reports}
    db.add_all([
        membership, future_registration, waiter_registration, past_registration, reaction, saved,
        preferences, discovery, notice, held_comment, scrubbed_comment, held_message,
        scrubbed_message, *reports,
    ])
    db.commit()

    receipt_id = _due_receipt(db, user)
    result = account_erasure.fulfill_erasure(receipt_id)

    assert result["status"] == "completed"
    assert result["counts"]["memberships_deactivated"] == 1
    assert result["counts"]["registrations_cancelled"] == 1
    assert result["counts"]["registrations_preserved"] == 1
    assert result["counts"]["comments_deidentified"] == 1
    assert result["counts"]["comments_held"] == 1
    assert result["counts"]["messages_deidentified"] == 1
    assert result["counts"]["messages_held"] == 1
    assert result["counts"]["reactions_removed"] == 1
    assert result["counts"]["private_rows_removed"] >= 4

    db.expire_all()
    assert db.get(User, user.id).active is False
    assert db.get(ErasedAccount, user.id) is not None
    assert db.get(Registration, future_registration.id).status == "cancelled"
    assert db.get(Registration, waiter_registration.id).status == "confirmed"
    preserved = db.get(Registration, past_registration.id)
    assert preserved.status == "confirmed" and preserved.persona_shared is False
    assert db.get(Event, future_event.id).interest_count == 0
    assert db.get(EventComment, held_comment.id).body == "reported comment"
    assert db.get(EventComment, held_comment.id).body_hash == "a" * 64
    scrubbed = db.get(EventComment, scrubbed_comment.id)
    assert scrubbed.body is None and scrubbed.removed_at is not None
    assert db.get(ChatMessage, held_message.id).body == "reported message"
    scrubbed = db.get(ChatMessage, scrubbed_message.id)
    assert scrubbed.body is None and scrubbed.removed_at is not None
    assert db.get(UserPreferences, user.id) is None
    assert db.get(UserDiscoveryPreferences, user.id) is None
    assert db.get(SavedEvent, (user.id, future_event.id)) is None
    assert db.get(Notification, notice_id) is None
    assert db.scalar(select(func.count()).select_from(EventReaction).where(
        EventReaction.user_id == user.id
    )) == 0
    completed = db.get(ErasureRequest, receipt_id)
    assert completed.user_id is None
    assert account_erasure.fulfill_erasure(receipt_id)["status"] == "completed"

    purge_at = deadline + timedelta(seconds=1)
    assert account_erasure.purge_erased_content(db, at=purge_at, limit=100) == 2
    db.expire_all()
    purged_comment = db.get(EventComment, held_comment.id)
    purged_message = db.get(ChatMessage, held_message.id)
    assert purged_comment.body is None and purged_comment.removed_at == purge_at
    assert purged_comment.body_hash != "a" * 64
    assert purged_message.body is None and purged_message.removed_at == purge_at
    assert purged_message.body_hash != "c" * 64
    assert db.get(ContentReport, report_ids["comment"]).evidence == "report snapshot comment"
    assert db.get(ContentReport, report_ids["message"]).evidence == "report snapshot message"
    assert account_erasure.purge_erased_content(db, at=purge_at, limit=100) == 0


def test_old_supabase_identity_cannot_reprovision_an_erased_user(db, make_user, monkeypatch):
    user = make_user()
    account_erasure._scrub_user(user)
    db.add(ErasedAccount(user_id=user.id, erased_at=now()))
    db.commit()
    old_email = user.email
    identity = supabase_auth.VerifiedSupabaseIdentity(
        user_id=user.id, email="restored@example.invalid", email_verified=True,
    )
    monkeypatch.setattr(supabase_auth, "verify_supabase_identity", lambda *_args: identity)

    with pytest.raises(DomainError) as error:
        supabase_auth.actor_from_supabase_token(db, "old.jwt.token", SimpleNamespace())

    assert error.value.code == "authentication_required"
    db.expire_all()
    assert db.get(User, user.id).active is False
    assert db.get(User, user.id).email == old_email


def test_provider_outage_keeps_erasure_incomplete_and_uses_apikey_only(db, make_user, monkeypatch):
    user = make_user()
    receipt_id = _due_receipt(db, user)
    secret = "sb_secret_0123456789fake"
    settings = SimpleNamespace(
        auth_provider="supabase", supabase_url="https://abcdefgh.supabase.co",
        supabase_storage_secret=secret,
    )
    monkeypatch.setattr(account_erasure, "get_settings", lambda: settings)

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("provider calls require explicit action")

    monkeypatch.setattr(account_erasure, "build_opener", unexpected_network)
    waiting = account_erasure.fulfill_erasure(receipt_id)
    assert waiting["status"] == "blocked"
    assert waiting["blocker_code"] == "provider_action_required"
    assert waiting["counts"] == {}

    class OutageOpener:
        def open(self, *_args, **_kwargs):
            raise URLError("offline")

    monkeypatch.setattr(account_erasure, "build_opener", lambda *_handlers: OutageOpener())
    failed = account_erasure.fulfill_erasure(receipt_id, explicit_provider_action=True)
    assert failed["status"] == "blocked"
    assert failed["blocker_code"] == "provider_revocation_failed"
    assert failed["counts"] == {}
    db.expire_all()
    assert db.get(ErasureRequest, receipt_id).user_id == user.id

    captured = {}

    class SuccessResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return self.status

    class SuccessOpener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return SuccessResponse()

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return SuccessOpener()

    monkeypatch.setattr(account_erasure, "build_opener", fake_build_opener)
    completed = account_erasure.fulfill_erasure(receipt_id, explicit_provider_action=True)

    request = captured["request"]
    assert completed["status"] == "completed"
    assert completed["counts"]
    assert request.method == "DELETE"
    assert request.get_header("Apikey") == secret
    assert request.get_header("Authorization") is None
    assert captured["timeout"] == 5
    assert any(isinstance(handler, account_erasure._NoRedirectHandler) for handler in captured["handlers"])
    assert account_erasure._NoRedirectHandler().redirect_request(
        request, None, 302, "Found", {}, "https://example.invalid/redirect"
    ) is None
    db.expire_all()
    assert db.get(ErasureRequest, receipt_id).user_id is None


def test_replay_target_matches_recovery_and_rejects_dev_and_test_databases():
    from app.recovery import validate_restore_database_url

    safe_url = "postgresql+psycopg://user:placeholder@127.0.0.1:5433/intraspot_restore_sprint28"
    assert account_erasure._validated_restore_url(safe_url).database == "intraspot_restore_sprint28"
    assert validate_restore_database_url(safe_url).database == "intraspot_restore_sprint28"

    for database in (
        "intraspot_mvp", "intraspot_real_dev", "intraspot_mvp_test", "intraspot_test",
        "intraspot_dev",
    ):
        url = f"postgresql+psycopg://user:placeholder@127.0.0.1:5433/{database}"
        with pytest.raises(ValueError):
            account_erasure._validated_restore_url(url)


def test_replay_is_idempotent_and_uses_tombstone_time(db, make_user, monkeypatch):
    user = make_user()
    requested_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    receipt = ErasureRequest(
        user_id=user.id, requested_at=requested_at, due_at=requested_at + timedelta(days=30),
        status="pending", counts={},
    )
    db.add(receipt)
    db.commit()
    database_url = "postgresql+psycopg://user:placeholder@127.0.0.1:5433/intraspot_restore_sprint28"
    erased_at = datetime(2026, 9, 15, 12, 30, tzinfo=timezone.utc)

    def isolated_test_engine(*_args, **kwargs):
        return sqlalchemy_create_engine(db.get_bind().url, **kwargs)

    monkeypatch.setattr(account_erasure, "create_engine", isolated_test_engine)
    records = [{"user_id": user.id, "erased_at": erased_at.isoformat()}]
    first = account_erasure.replay_erasures(records, database_url)
    second = account_erasure.replay_erasures(records, database_url)

    assert first == second == {"applied": 1, "created_tombstone_users": 0}
    db.expire_all()
    assert db.get(User, user.id).active is False
    assert db.get(ErasedAccount, user.id).erased_at == erased_at
    completed = db.get(ErasureRequest, receipt.id)
    assert completed.status == "completed"
    assert completed.completed_at == erased_at
    assert completed.user_id is None
    assert account_erasure.export_tombstones(db) == [
        {"user_id": user.id, "erased_at": erased_at.isoformat()}
    ]


def test_receipt_purge_keeps_completed_receipts_for_365_days(db, make_user):
    at = now()
    user = make_user()
    old = ErasureRequest(
        user_id=None, requested_at=at - timedelta(days=400), due_at=at - timedelta(days=370),
        completed_at=at - timedelta(days=365), status="completed", counts={},
    )
    recent = ErasureRequest(
        user_id=None, requested_at=at - timedelta(days=390), due_at=at - timedelta(days=360),
        completed_at=at - timedelta(days=364), status="completed", counts={},
    )
    blocked = ErasureRequest(
        user_id=user.id, requested_at=at - timedelta(days=400), due_at=at - timedelta(days=370),
        status="blocked", counts={},
    )
    db.add_all([old, recent, blocked])
    db.commit()

    assert account_erasure.purge_erasure_receipts(db, at=at, limit=10) == 1
    assert db.get(ErasureRequest, old.id) is None
    assert db.get(ErasureRequest, recent.id) is not None
    assert db.get(ErasureRequest, blocked.id) is not None

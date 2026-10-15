from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event as ThreadEvent
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select

from app.core.communication_schemas import ContentCreate, ContentItem
from app.core.errors import DomainError
from app.db.models import now, uid
from app.db.session import engine, session_factory
from app.notifications import Notification
from app.domains.chat import service
from app.domains.chat.models import ChatMessage
from app.domains.chat.schemas import ChatInboxItem
from app.domains.events.models import Event
from app.domains.moderation.models import ContentHide, ContentReport
from app.domains.registrations.models import Registration


def _register(db, event, user, *, status='confirmed', persona_shared=False):
    existing = db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event.id)) or 0
    registration = Registration(
        id=uid(),
        user_id=user.id,
        event_id=event.id,
        status=status,
        admission_order=existing + 1,
        persona_shared=persona_shared,
    )
    db.add(registration)
    db.commit()
    return registration


def _payload(body='A short fictional message.', key=None):
    return ContentCreate(body=body, client_key=key or uuid4())


def test_shared_content_types_are_reexported_without_chat_duplicates():
    from app.domains.chat.schemas import ContentCreate as ChatContentCreate
    from app.domains.chat.schemas import ContentPage as ChatContentPage

    from app.core.communication_schemas import ContentPage

    assert ChatContentCreate is ContentCreate
    assert ChatContentPage is ContentPage
    assert ContentItem.__module__ == 'app.core.communication_schemas'


@pytest.mark.parametrize('status', ['pending', 'waitlisted', 'cancelled', 'reconfirmation_required', 'rejected'])
def test_nonconfirmed_registration_cannot_read_chat(db, make_event, make_user, status):
    event = make_event()
    attendee = make_user()
    _register(db, event, attendee, status=status)

    with pytest.raises(DomainError) as denied:
        service.get_chat_thread(db, event.id, attendee.id)
    assert (denied.value.code, denied.value.status) == ('chat_access_forbidden', 403)


def test_event_owner_and_confirmed_user_on_draft_do_not_bypass_access_rules(db, make_event, make_user):
    event = make_event()
    owner = db.get(type(event), event.id)
    with pytest.raises(DomainError) as owner_denied:
        service.get_chat_thread(db, event.id, owner.created_by)
    assert (owner_denied.value.code, owner_denied.value.status) == ('chat_access_forbidden', 403)

    draft = make_event(status='draft')
    attendee = make_user()
    _register(db, draft, attendee)
    with pytest.raises(DomainError) as draft_denied:
        service.get_chat_thread(db, draft.id, attendee.id)
    assert (draft_denied.value.code, draft_denied.value.status) == ('event_not_found', 404)


def test_event_end_archives_and_exact_retention_cutoff_expires_and_purges(db, make_event, make_user):
    event = make_event()
    attendee = make_user()
    other_attendee = make_user()
    _register(db, event, attendee)
    _register(db, event, other_attendee)
    message = service.send_chat_message(
        db,
        event.id,
        attendee.id,
        _payload('Report evidence is stored separately.'),
        at=event.ends_at - timedelta(minutes=1),
    )
    hide = ContentHide(
        id=uid(), user_id=other_attendee.id, event_id=event.id,
        kind='message', target_id=message.id,
    )
    report = ContentReport(
        id=uid(), event_id=event.id, org_id=event.org_id,
        reporter_id=other_attendee.id, subject_user_id=attendee.id,
        kind='message', target_id=message.id, reason='harassment',
        status='open', stage='organization',
        evidence='bounded retained review evidence',
        deadline=event.ends_at + timedelta(days=7),
    )
    db.add_all([hide, report])
    db.commit()

    at_end = event.ends_at
    thread = service.get_chat_thread(db, event.id, attendee.id, at=at_end)
    assert thread.status == 'archived'
    assert thread.can_send is False
    assert service.list_chat_inbox(db, attendee.id, at=at_end)[0].status == 'archived'
    with pytest.raises(DomainError) as read_only:
        service.send_chat_message(db, event.id, attendee.id, _payload('Too late.'), at=at_end)
    assert (read_only.value.code, read_only.value.status) == ('chat_read_only', 403)

    deletes_at = event.ends_at + service.CHAT_RETENTION
    assert len(service.get_chat_thread(db, event.id, attendee.id, at=deletes_at - timedelta(microseconds=1)).items) == 1
    with pytest.raises(DomainError) as expired:
        service.get_chat_thread(db, event.id, attendee.id, at=deletes_at)
    assert (expired.value.code, expired.value.status) == ('chat_expired', 404)
    assert service.purge_event_chat_locked(db, event, deletes_at - timedelta(microseconds=1)) == 0
    assert db.scalar(select(func.count(ContentHide.id)).where(ContentHide.target_id == message.id)) == 1

    locked_event = db.scalar(select(Event).where(Event.id == event.id).with_for_update())
    assert service.purge_event_chat_locked(db, locked_event, deletes_at) == 1
    db.expire_all()
    assert db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.event_id == event.id)) == 0
    assert db.scalar(select(func.count(ContentHide.id)).where(ContentHide.target_id == message.id)) == 0
    retained_report = db.get(ContentReport, report.id)
    assert retained_report is not None
    assert retained_report.evidence == 'bounded retained review evidence'


def test_revocation_reconfirmation_and_person_report_restriction(db, make_event, make_user):
    event = make_event()
    attendee = make_user()
    reporter = make_user()
    _register(db, event, attendee)
    _register(db, event, reporter)

    assert service.get_chat_thread(db, event.id, attendee.id).can_send is True
    retry_payload = _payload('A fictional message sent before restriction.', uuid4())
    original = service.send_chat_message(db, event.id, attendee.id, retry_payload)
    db.commit()
    registration = db.scalar(select(Registration).where(
        Registration.event_id == event.id,
        Registration.user_id == attendee.id,
    ))
    registration.status = 'reconfirmation_required'
    db.commit()
    with pytest.raises(DomainError) as revoked:
        service.get_chat_thread(db, event.id, attendee.id)
    assert revoked.value.code == 'chat_access_forbidden'

    registration.status = 'confirmed'
    db.commit()
    report = ContentReport(
        id=uid(), event_id=event.id, org_id=event.org_id,
        reporter_id=reporter.id, subject_user_id=attendee.id,
        kind='person', target_id=attendee.id, reason='harassment',
        status='open', stage='platform', deadline=event.ends_at,
    )
    db.add(report)
    db.commit()

    assert service.get_chat_thread(db, event.id, attendee.id, communication_restricted=True).can_send is False
    retry = service.send_chat_message(db, event.id, attendee.id, retry_payload)
    assert retry.id == original.id
    assert db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.event_id == event.id)) == 1
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.event_id == event.id,
        Notification.kind == 'chat_message',
    )) == 1

    with pytest.raises(DomainError) as restricted:
        service.send_chat_message(db, event.id, attendee.id, _payload())
    assert (restricted.value.code, restricted.value.status) == ('personal_review_pending', 403)

    registration.status = 'reconfirmation_required'
    db.commit()
    with pytest.raises(DomainError) as no_longer_confirmed:
        service.send_chat_message(db, event.id, attendee.id, retry_payload)
    assert (no_longer_confirmed.value.code, no_longer_confirmed.value.status) == ('chat_access_forbidden', 403)

    registration.status = 'confirmed'
    db.delete(report)
    db.commit()
    assert service.get_chat_thread(db, event.id, attendee.id).can_send is True
    sent = service.send_chat_message(db, event.id, attendee.id, _payload())
    assert sent.mine is True


def test_idempotent_retries_conflict_detection_and_single_generic_notice(db, make_event, make_user):
    event = make_event()
    author = make_user()
    recipient = make_user()
    _register(db, event, author)
    _register(db, event, recipient)
    payload = _payload('Same fictional message.', uuid4())

    first = service.send_chat_message(db, event.id, author.id, payload)
    db.commit()
    retry = service.send_chat_message(db, event.id, author.id, payload)
    assert retry.id == first.id
    with pytest.raises(DomainError) as mismatch:
        service.send_chat_message(db, event.id, author.id, _payload('Different fictional message.', payload.client_key))
    assert (mismatch.value.code, mismatch.value.status) == ('idempotency_key_reused', 409)

    assert db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.event_id == event.id)) == 1
    notices = db.scalars(select(Notification).where(
        Notification.event_id == event.id,
        Notification.kind == 'chat_message',
    )).all()
    assert len(notices) == 1
    assert notices[0].user_id == recipient.id
    assert notices[0].message == 'New message in an event chat.'
    assert first.body == 'Same fictional message.'


def test_concurrent_same_client_key_creates_one_message_and_one_notice(db, make_event, make_user):
    event = make_event()
    author = make_user()
    recipient = make_user()
    _register(db, event, author)
    _register(db, event, recipient)
    payload = _payload('One concurrent fictional message.', uuid4())
    barrier = Barrier(2)

    def submit(_):
        barrier.wait(timeout=10)
        with session_factory()() as concurrent_db:
            try:
                result = service.send_chat_message(concurrent_db, event.id, author.id, payload)
                concurrent_db.commit()
                return result.id
            except Exception:
                concurrent_db.rollback()
                raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(submit, range(2)))

    assert ids[0] == ids[1]
    assert db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.event_id == event.id)) == 1
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.event_id == event.id,
        Notification.kind == 'chat_message',
    )) == 1


@pytest.mark.parametrize(
    ('boundary', 'expected_code'),
    [('scheduled_end', 'chat_read_only'), ('deletion_cutoff', 'chat_expired')],
)
def test_send_samples_clock_after_blocking_event_lock(db, make_event, make_user, monkeypatch, boundary, expected_code):
    event = make_event()
    attendee = make_user()
    _register(db, event, attendee)
    locked_event = db.scalar(select(Event).where(Event.id == event.id).with_for_update())
    assert locked_event is not None

    boundary_at = event.ends_at if boundary == 'scheduled_end' else event.ends_at + service.CHAT_RETENTION
    clock_sampled = ThreadEvent()
    lock_query_attempted = ThreadEvent()

    def fixed_live_clock():
        clock_sampled.set()
        return boundary_at

    def observe_lock_attempt(_connection, _cursor, statement, _parameters, _context, _executemany):
        normalized = statement.lower()
        if 'events' in normalized and 'for update' in normalized:
            lock_query_attempted.set()

    monkeypatch.setattr(service, 'now', fixed_live_clock)
    database_engine = engine()
    sqlalchemy_event.listen(database_engine, 'before_cursor_execute', observe_lock_attempt)

    def submit():
        with session_factory()() as concurrent_db:
            try:
                service.send_chat_message(concurrent_db, event.id, attendee.id, _payload())
                concurrent_db.commit()
                return None
            except DomainError as error:
                concurrent_db.rollback()
                return error.code, error.status

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(submit)
        try:
            assert lock_query_attempted.wait(timeout=10)
            # The worker has issued the blocking SELECT FOR UPDATE. Its clock
            # must not be sampled until this test releases the held event row.
            assert not clock_sampled.is_set()
        finally:
            db.commit()
        assert future.result(timeout=10) == (
            expected_code,
            404 if expected_code == 'chat_expired' else 403,
        )
    finally:
        sqlalchemy_event.remove(database_engine, 'before_cursor_execute', observe_lock_attempt)
        db.rollback()
        pool.shutdown(wait=True, cancel_futures=True)

    assert clock_sampled.is_set() is True
    assert db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.event_id == event.id)) == 0


def test_cursor_paging_is_chronological_and_inbox_contains_only_metadata(db, make_event, make_user):
    event = make_event()
    author = make_user(nickname='Private fictional nickname', email='private-fixture@students.plm.edu.ph')
    viewer = make_user(nickname='Viewer private nickname', email='viewer-fixture@students.plm.edu.ph')
    _register(db, event, author)
    _register(db, event, viewer)
    messages = [
        service.send_chat_message(db, event.id, author.id, _payload(f'Fictional body {index}.'))
        for index in range(1, 4)
    ]
    db.commit()

    latest = service.get_chat_thread(db, event.id, viewer.id, limit=2)
    assert [item.sequence for item in latest.items] == [messages[1].sequence, messages[2].sequence]
    assert latest.next_before == messages[1].sequence
    assert [item.body for item in latest.items] == ['Fictional body 2.', 'Fictional body 3.']
    assert all(item.author_label == 'PLM member' for item in latest.items)

    older = service.get_chat_thread(
        db, event.id, viewer.id, before_sequence=latest.next_before, limit=2,
    )
    assert [item.sequence for item in older.items] == [messages[0].sequence]
    newer = service.get_chat_thread(db, event.id, viewer.id, after_sequence=messages[0].sequence, limit=2)
    assert [item.sequence for item in newer.items] == [messages[1].sequence, messages[2].sequence]
    with pytest.raises(DomainError) as invalid:
        service.get_chat_thread(
            db, event.id, viewer.id,
            after_sequence=messages[0].sequence,
            before_sequence=messages[2].sequence,
        )
    assert invalid.value.status == 422

    inbox = service.list_chat_inbox(db, viewer.id)[0]
    assert isinstance(inbox, ChatInboxItem)
    inbox_dump = inbox.model_dump(mode='json')
    assert set(inbox_dump) == {
        'event_id', 'event_title', 'organization_name', 'ends_at',
        'deletes_at', 'status', 'latest_at',
    }
    assert inbox_dump['latest_at'] is not None
    assert 'body' not in inbox_dump
    serialized = str(latest.model_dump(mode='json'))
    assert author.email not in serialized and viewer.email not in serialized
    assert 'Private fictional nickname' not in serialized
    assert 'Viewer private nickname' not in serialized

    hide = ContentHide(
        id=uid(), user_id=viewer.id, event_id=event.id,
        kind='message', target_id=messages[2].id,
    )
    db.add(hide)
    db.commit()
    hidden_page = service.get_chat_thread(db, event.id, viewer.id, limit=2)
    hidden_item = next(item for item in hidden_page.items if item.id == messages[2].id)
    assert hidden_item.body is None
    assert hidden_item.locally_hidden is True


def test_after_cursor_includes_retained_tombstone_ids_without_old_body(db, make_event, make_user):
    event = make_event()
    author = make_user()
    viewer = make_user()
    _register(db, event, author)
    _register(db, event, viewer)
    removed_message = service.send_chat_message(db, event.id, author.id, _payload('This body must be cleared.'))
    newer_message = service.send_chat_message(db, event.id, author.id, _payload('This newer body remains.'))
    db.commit()

    locked_event = db.scalar(select(Event).where(Event.id == event.id).with_for_update())
    assert service.remove_message_locked(db, removed_message.id, locked_event.id, at=now()) is not None
    db.commit()

    page = service.get_chat_thread(db, event.id, viewer.id, after_sequence=removed_message.sequence)
    assert page.removed_ids == [removed_message.id]
    assert [item.id for item in page.items] == [newer_message.id]
    assert page.items[0].body == 'This newer body remains.'
    assert 'This body must be cleared.' not in str(page.model_dump(mode='json'))

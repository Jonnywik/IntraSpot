from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import now, uid
from app.db.session import session_factory
from app.domains.events.models import Event
from app.domains.moderation.models import ContentHide, ContentReport, ReportDecision
from app.domains.moderation import service as moderation_service
from app.domains.moderation.service import (
    catch_up_reports_locked,
    create_report,
    has_pending_person_report,
    set_content_hide,
)
from app.domains.social.models import EventComment
from app.domains.social.service import list_comments
from app.notifications import Notification


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def actor_for(user):
    return Actor(
        user_id=user.id,
        nickname=user.nickname,
        eligible=True,
        profile_complete=True,
        platform_admin=user.platform_admin,
    )


def add_comment(db, event, author, body='A visible fictional comment.'):
    comment = EventComment(
        id=uid(),
        event_id=event.id,
        author_id=author.id,
        body=body,
        body_hash='a' * 64,
        client_key=uid(),
        created_at=now(),
    )
    db.add(comment)
    db.commit()
    return comment


def test_comment_report_routes_to_org_and_isolated_review_queues(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization)
    reporter = make_user()
    subject = make_user()
    comment = add_comment(db, event, subject)
    outsider = make_user()
    platform_admin = make_user(platform_admin=True)

    response = client.post(
        f'/api/v1/events/{event.id}/reports',
        headers=auth(token_for(reporter)),
        json={'kind': 'comment', 'target_id': comment.id, 'reason': 'spam'},
    )
    assert response.status_code == 201
    receipt = response.json()
    assert receipt['status'] == 'open'
    assert receipt['stage'] == 'organization'

    org_queue = client.get(
        f'/api/v1/moderation/reports?org_id={organization.id}',
        headers=auth(token_for(owner)),
    )
    assert org_queue.status_code == 200
    assert len(org_queue.json()) == 1
    assert org_queue.json()[0]['evidence'] == comment.body

    forbidden = client.get(
        f'/api/v1/moderation/reports?org_id={organization.id}',
        headers=auth(token_for(outsider)),
    )
    assert forbidden.status_code == 403

    platform_queue = client.get(
        f'/api/v1/moderation/reports?org_id={organization.id}',
        headers=auth(token_for(platform_admin)),
    )
    assert platform_queue.status_code == 200
    assert platform_queue.json() == []

    decisions_before = db.scalar(select(func.count()).select_from(ReportDecision))
    notices_before = db.scalar(select(func.count()).select_from(Notification))
    forbidden_decision = client.post(
        f"/api/v1/moderation/reports/{receipt['id']}/decision",
        headers=auth(token_for(outsider)),
        json={'action': 'dismiss'},
    )
    assert forbidden_decision.status_code == 403
    assert db.scalar(select(func.count()).select_from(ReportDecision)) == decisions_before
    assert db.scalar(select(func.count()).select_from(Notification)) == notices_before

    own_reports = client.get('/api/v1/me/reports', headers=auth(token_for(reporter)))
    assert own_reports.status_code == 200
    assert own_reports.json()[0]['id'] == receipt['id']
    assert 'reason' not in own_reports.json()[0]
    assert 'evidence' not in own_reports.json()[0]


def test_person_reports_require_visible_event_evidence_and_use_platform_review(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization)
    reporter = make_user()
    subject = make_user()
    visible_comment = add_comment(db, event, subject)
    self_comment = add_comment(db, event, reporter)
    arbitrary_user = make_user()

    response = client.post(
        f'/api/v1/events/{event.id}/reports',
        headers=auth(token_for(reporter)),
        json={'kind': 'person', 'target_id': subject.id, 'reason': 'impersonation'},
    )
    assert response.status_code == 201
    receipt = response.json()
    assert receipt['stage'] == 'platform'
    assert has_pending_person_report(db, subject.id)

    org_queue = client.get(
        f'/api/v1/moderation/reports?org_id={organization.id}',
        headers=auth(token_for(owner)),
    )
    assert org_queue.status_code == 200
    assert all(item['id'] != receipt['id'] for item in org_queue.json())

    org_detail = client.get(
        f"/api/v1/moderation/reports/{receipt['id']}",
        headers=auth(token_for(owner)),
    )
    assert org_detail.status_code == 403

    reports_before = db.scalar(select(func.count()).select_from(ContentReport))
    notices_before = db.scalar(select(func.count()).select_from(Notification))
    self_report = client.post(
        f'/api/v1/events/{event.id}/reports',
        headers=auth(token_for(reporter)),
        json={'kind': 'person', 'target_id': reporter.id, 'reason': 'other'},
    )
    assert self_report.status_code == 403
    ungrounded = client.post(
        f'/api/v1/events/{event.id}/reports',
        headers=auth(token_for(reporter)),
        json={'kind': 'person', 'target_id': arbitrary_user.id, 'reason': 'other'},
    )
    assert ungrounded.status_code == 404
    assert db.scalar(select(func.count()).select_from(ContentReport)) == reports_before
    assert db.scalar(select(func.count()).select_from(Notification)) == notices_before
    assert self_comment.id != visible_comment.id


def test_content_hides_are_private_to_the_requesting_user(db, make_user, make_org, make_event):
    event = make_event(org=make_org())
    author = make_user()
    hider = make_user()
    other_viewer = make_user()
    comment = add_comment(db, event, author, 'Local-only hide proof.')

    assert set_content_hide(
        db, actor_for(hider), event.id, 'comment', comment.id, True,
    ) == {'hidden': True}
    db.flush()
    assert db.scalar(select(ContentHide.id).where(
        ContentHide.user_id == hider.id,
        ContentHide.kind == 'comment',
        ContentHide.target_id == comment.id,
    )) is not None

    hidden_page = list_comments(db, event.id, actor_for(hider))
    other_page = list_comments(db, event.id, actor_for(other_viewer))
    assert hidden_page.items[0].body is None
    assert hidden_page.items[0].locally_hidden is True
    assert other_page.items[0].body == comment.body
    assert other_page.items[0].locally_hidden is False

    set_content_hide(db, actor_for(hider), event.id, 'comment', comment.id, False)
    db.flush()
    assert list_comments(db, event.id, actor_for(hider)).items[0].body == comment.body


def test_unconfirmed_chat_actor_cannot_report_or_hide_messages(db, make_user, make_org, make_event):
    event = make_event(org=make_org())
    actor = actor_for(make_user())
    message_id = uid()
    reports_before = db.scalar(select(func.count()).select_from(ContentReport))
    hides_before = db.scalar(select(func.count()).select_from(ContentHide))
    notices_before = db.scalar(select(func.count()).select_from(Notification))

    with pytest.raises(DomainError) as report_error:
        create_report(db, actor, event.id, 'message', message_id, 'spam')
    assert report_error.value.code == 'chat_access_forbidden'

    with pytest.raises(DomainError) as hide_error:
        set_content_hide(db, actor, event.id, 'message', message_id, True)
    assert hide_error.value.code == 'chat_access_forbidden'
    assert db.scalar(select(func.count()).select_from(ContentReport)) == reports_before
    assert db.scalar(select(func.count()).select_from(ContentHide)) == hides_before
    assert db.scalar(select(func.count()).select_from(Notification)) == notices_before


def test_report_deadlines_clear_evidence_and_never_auto_remove_content(
    db, make_user, make_org, make_event
):
    event = make_event(org=make_org())
    reporter = make_user()
    subject = make_user()
    comment = add_comment(db, event, subject, 'Retained moderation snapshot.')
    timestamp = now()

    content_report = create_report(
        db, actor_for(reporter), event.id, 'comment', comment.id, 'harassment', at=timestamp,
    )
    person_report = create_report(
        db, actor_for(reporter), event.id, 'person', subject.id, 'impersonation', at=timestamp,
    )
    personal_deadline = timestamp + timedelta(days=14)
    assert has_pending_person_report(db, subject.id, at=personal_deadline - timedelta(microseconds=1))
    assert not has_pending_person_report(db, subject.id, at=personal_deadline)

    db.commit()
    locked_event = db.scalar(select(Event).where(Event.id == event.id).with_for_update())
    assert catch_up_reports_locked(db, locked_event, at=personal_deadline) == 2
    db.flush()

    content_row = db.get(ContentReport, content_report['id'])
    person_row = db.get(ContentReport, person_report['id'])
    assert content_row.status == 'escalated'
    assert content_row.deadline == timestamp + timedelta(days=21)
    assert content_row.evidence == comment.body
    assert person_row.status == 'expired'
    assert person_row.evidence is None
    assert not has_pending_person_report(db, subject.id, at=personal_deadline)

    locked_event = db.scalar(select(Event).where(Event.id == event.id).with_for_update())
    assert catch_up_reports_locked(db, locked_event, at=timestamp + timedelta(days=21)) == 1
    db.flush()
    db.refresh(content_row)
    db.refresh(comment)
    assert content_row.status == 'expired'
    assert content_row.evidence is None
    assert comment.removed_at is None
    assert comment.body == 'Retained moderation snapshot.'

    decisions = list(db.scalars(select(ReportDecision).where(
        ReportDecision.report_id.in_([content_report['id'], person_report['id']]),
    )))
    assert any(item.action == 'escalate' and item.reviewer_id is None for item in decisions)
    assert any(item.action == 'expire' and item.reviewer_id is None for item in decisions)


def test_reported_content_stays_visible_until_an_authorized_removal(
    db, make_user, make_org, make_event
):
    owner = make_user()
    event = make_event(org=make_org(owner=owner))
    reporter = make_user()
    subject = make_user()
    comment = add_comment(db, event, subject, 'Visible pending moderator review.')
    created_at = now()
    receipt = create_report(
        db, actor_for(reporter), event.id, 'comment', comment.id, 'harassment', at=created_at,
    )
    db.refresh(comment)
    assert comment.body == 'Visible pending moderator review.'
    assert comment.removed_at is None

    removed = moderation_service.decide_report(
        db,
        actor_for(owner),
        receipt['id'],
        'remove',
        at=created_at + timedelta(days=1),
    )
    db.refresh(comment)
    assert removed['status'] == 'removed'
    assert removed['evidence'] is None
    assert comment.body is None
    assert comment.removed_at == created_at + timedelta(days=1)


def test_manual_escalation_starts_a_full_platform_window_from_the_decision_time(
    db, make_user, make_org, make_event
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization)
    reporter = make_user()
    subject = make_user()
    platform_admin = make_user(platform_admin=True)
    comment = add_comment(db, event, subject, 'Evidence for manual escalation.')
    created_at = now()
    initial = create_report(
        db, actor_for(reporter), event.id, 'comment', comment.id, 'harassment', at=created_at,
    )
    decision_at = created_at + timedelta(days=1)

    escalated = moderation_service.decide_report(
        db, actor_for(owner), initial['id'], 'escalate', at=decision_at,
    )
    assert escalated['status'] == 'escalated'
    assert escalated['stage'] == 'platform'
    assert escalated['deadline'] == decision_at + timedelta(days=14)
    assert escalated['evidence'] == comment.body

    decisions_before = db.scalar(select(func.count()).select_from(ReportDecision))
    notices_before = db.scalar(select(func.count()).select_from(Notification))
    with pytest.raises(DomainError):
        moderation_service.decide_report(
            db,
            actor_for(owner),
            initial['id'],
            'dismiss',
            at=decision_at + timedelta(days=1),
        )
    assert db.scalar(select(func.count()).select_from(ReportDecision)) == decisions_before
    assert db.scalar(select(func.count()).select_from(Notification)) == notices_before

    closed = moderation_service.decide_report(
        db,
        actor_for(platform_admin),
        initial['id'],
        'dismiss',
        at=decision_at + timedelta(days=1),
    )
    assert closed['status'] == 'dismissed'
    assert closed['evidence'] is None


def test_create_and_hide_timestamps_are_sampled_after_their_write_locks(
    db, make_user, make_org, make_event, monkeypatch
):
    event = make_event(org=make_org())
    reporter = make_user()
    subject = make_user()
    comment = add_comment(db, event, subject, 'Timestamp lock proof.')
    before_lock_time = now()
    after_lock_time = before_lock_time + timedelta(seconds=5)
    lock_state = {'report': False, 'user': False, 'hide': False, 'require_user': False}

    def clock_after_locks():
        report_locks_ready = lock_state['report'] and (
            not lock_state['require_user'] or lock_state['user']
        )
        if report_locks_ready or lock_state['hide']:
            return after_lock_time
        return before_lock_time

    real_active_report = moderation_service._active_report

    def track_report_lock(*args, **kwargs):
        result = real_active_report(*args, **kwargs)
        if kwargs.get('lock'):
            lock_state['report'] = True
        return result

    monkeypatch.setattr(moderation_service, 'now', clock_after_locks)
    monkeypatch.setattr(moderation_service, '_active_report', track_report_lock)
    receipt = create_report(
        db, actor_for(reporter), event.id, 'comment', comment.id, 'spam',
    )
    report = db.get(ContentReport, receipt['id'])
    assert report.created_at == after_lock_time

    lock_state.update(report=False, user=False, require_user=True)
    real_lock_user = moderation_service._lock_user

    def track_user_lock(*args, **kwargs):
        result = real_lock_user(*args, **kwargs)
        lock_state['user'] = True
        return result

    monkeypatch.setattr(moderation_service, '_lock_user', track_user_lock)
    person_receipt = create_report(
        db, actor_for(reporter), event.id, 'person', subject.id, 'impersonation',
    )
    person_report = db.get(ContentReport, person_receipt['id'])
    assert person_report.created_at == after_lock_time

    lock_state.update(report=False, user=False, hide=False, require_user=False)
    real_scalar = db.scalar

    def track_hide_lock(statement, *args, **kwargs):
        result = real_scalar(statement, *args, **kwargs)
        if getattr(statement, '_for_update_arg', None) is not None and 'content_hides' in str(statement).lower():
            lock_state['hide'] = True
        return result

    monkeypatch.setattr(db, 'scalar', track_hide_lock)
    set_content_hide(db, actor_for(reporter), event.id, 'comment', comment.id, True)
    hide = db.scalar(select(ContentHide).where(
        ContentHide.user_id == reporter.id,
        ContentHide.kind == 'comment',
        ContentHide.target_id == comment.id,
    ))
    assert hide.created_at == after_lock_time


def test_decision_deadline_is_checked_against_clock_after_report_lock(
    db, make_user, make_org, make_event, monkeypatch
):
    owner = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization)
    reporter = make_user()
    subject = make_user()
    comment = add_comment(db, event, subject, 'Decision deadline proof.')
    before_lock_time = now()
    initial = create_report(
        db, actor_for(reporter), event.id, 'comment', comment.id, 'harassment', at=before_lock_time,
    )
    report = db.get(ContentReport, initial['id'])
    report.deadline = before_lock_time + timedelta(seconds=1)
    db.commit()

    before_deadline = before_lock_time + timedelta(microseconds=500_000)
    after_deadline = before_lock_time + timedelta(seconds=2)
    lock_state = {'report': False}
    real_scalar = db.scalar

    def track_report_lock(statement, *args, **kwargs):
        result = real_scalar(statement, *args, **kwargs)
        statement_sql = str(statement).lower()
        if getattr(statement, '_for_update_arg', None) is not None and 'content_reports' in statement_sql:
            lock_state['report'] = True
        return result

    def clock_after_report_lock():
        return after_deadline if lock_state['report'] else before_deadline

    monkeypatch.setattr(db, 'scalar', track_report_lock)
    monkeypatch.setattr(moderation_service, 'now', clock_after_report_lock)
    decisions_before = db.scalar(select(func.count()).select_from(ReportDecision))
    notices_before = db.scalar(select(func.count()).select_from(Notification))

    with pytest.raises(DomainError) as raised:
        moderation_service.decide_report(db, actor_for(owner), initial['id'], 'dismiss')

    assert raised.value.code == 'report_deadline_expired'
    assert db.scalar(select(func.count()).select_from(ReportDecision)) == decisions_before
    assert db.scalar(select(func.count()).select_from(Notification)) == notices_before
    assert db.get(ContentReport, initial['id']).status == 'open'


def test_concurrent_person_reports_share_one_active_case(
    db, make_user, make_org, make_event
):
    organization = make_org()
    event_one = make_event(org=organization)
    event_two = make_event(org=organization)
    reporter = make_user()
    subject = make_user()
    comment_one = add_comment(db, event_one, subject, 'Visible in first event.')
    comment_two = add_comment(db, event_two, subject, 'Visible in second event.')
    actor = actor_for(reporter)
    barrier = Barrier(2)

    def submit(event_id):
        barrier.wait()
        with session_factory()() as concurrent_db:
            with concurrent_db.begin():
                return create_report(
                    concurrent_db,
                    actor,
                    event_id,
                    'person',
                    subject.id,
                    'impersonation',
                )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(submit, event_one.id)
        second = pool.submit(submit, event_two.id)
        first_receipt, second_receipt = first.result(), second.result()

    assert first_receipt['id'] == second_receipt['id']
    assert db.scalar(select(func.count()).select_from(ContentReport).where(
        ContentReport.reporter_id == reporter.id,
        ContentReport.kind == 'person',
        ContentReport.target_id == subject.id,
        ContentReport.status.in_(('open', 'escalated')),
    )) == 1
    assert comment_one.id != comment_two.id

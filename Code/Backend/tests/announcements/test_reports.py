import json
from datetime import timedelta

from sqlalchemy import func, select

from app.core.contracts import Actor
from app.db.models import now, uid
from app.domains.announcements.models import AnnouncementRevision
from app.domains.announcements.moderation_models import (
    AnnouncementReport,
    AnnouncementReportDecision,
)
from app.domains.announcements.report_service import (
    catch_up_announcement_reports_locked,
    create_announcement_report,
    decide_announcement_report,
    get_announcement_moderation_report,
)
from app.domains.organizations.service import get_organization
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


def publish_announcement(client, organization, owner, token_for, *, title='Original title', body='Original body'):
    response = client.post(
        f'/api/v1/organizations/{organization.id}/announcements',
        headers=auth(token_for(owner)),
        json={
            'title': title,
            'body': body,
            'audience': 'public',
            'client_key': uid(),
        },
    )
    assert response.status_code == 201
    return response.json()


def submit_report(client, announcement_id, reporter, token_for, reason='spam'):
    return client.post(
        f'/api/v1/announcements/{announcement_id}/reports',
        headers=auth(token_for(reporter)),
        json={'reason': reason},
    )


def count_rows(db, model, *criteria):
    statement = select(func.count()).select_from(model)
    for criterion in criteria:
        statement = statement.where(criterion)
    return db.scalar(statement)


def test_report_receipt_is_idempotent_and_notification_has_organization_context(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    reporter = make_user()
    admin = make_user(platform_admin=True)

    first = submit_report(client, announcement['id'], reporter, token_for)
    retry = submit_report(client, announcement['id'], reporter, token_for)
    assert first.status_code == retry.status_code == 201
    receipt = first.json()
    assert retry.json()['id'] == receipt['id']
    assert set(receipt) == {'id', 'announcement_id', 'org_id', 'status', 'deadline'}
    assert count_rows(
        db,
        AnnouncementReport,
        AnnouncementReport.reporter_id == reporter.id,
        AnnouncementReport.announcement_id == announcement['id'],
    ) == 1

    notices = client.get('/api/v1/me/notifications', headers=auth(token_for(reporter)))
    assert notices.status_code == 200
    safety_notice = next(item for item in notices.json() if item['kind'] == 'safety_report')
    assert safety_notice['event_id'] is None
    assert safety_notice['org_id'] == organization.id
    assert safety_notice['message'] == 'Your announcement safety report was received.'
    admin_notices = client.get('/api/v1/me/notifications', headers=auth(token_for(admin)))
    assert admin_notices.status_code == 200
    assert any(
        item['kind'] == 'safety_report'
        and item['org_id'] == organization.id
        and item['message'] == 'An announcement safety report requires platform review.'
        for item in admin_notices.json()
    )

    own_receipts = client.get('/api/v1/me/announcement-reports', headers=auth(token_for(reporter)))
    assert own_receipts.status_code == 200
    assert own_receipts.json()[0]['id'] == receipt['id']
    assert 'evidence' not in own_receipts.json()[0]
    assert 'reason' not in own_receipts.json()[0]


def test_report_requires_eligible_actor_and_cannot_target_own_announcement(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    ineligible = make_user(email='fictional-outsider@example.org')

    self_report = submit_report(client, announcement['id'], owner, token_for)
    unverified_report = submit_report(client, announcement['id'], ineligible, token_for)
    assert self_report.status_code == 403
    assert self_report.json()['error']['code'] == 'self_report_forbidden'
    assert unverified_report.status_code == 403
    assert unverified_report.json()['error']['code'] == 'plm_email_required'
    assert count_rows(db, AnnouncementReport) == 0
    assert count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report') == 0


def test_each_open_case_keeps_its_own_exact_snapshot_after_a_later_edit(
    client, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(
        client, organization, owner, token_for,
        title='First title', body='First body, kept only as report evidence.',
    )
    first_reporter = make_user()
    second_reporter = make_user()
    admin = make_user(platform_admin=True)
    first = submit_report(client, announcement['id'], first_reporter, token_for).json()
    second = submit_report(client, announcement['id'], second_reporter, token_for, 'harassment').json()

    edited = client.patch(
        f"/api/v1/announcements/{announcement['id']}",
        headers=auth(token_for(owner)) | {'If-Match': '"1"'},
        json={'title': 'Later title', 'body': 'Later body.'},
    )
    assert edited.status_code == 200
    assert edited.json()['version'] == 2

    for report in (first, second):
        detail = client.get(
            f"/api/v1/moderation/announcement-reports/{report['id']}",
            headers=auth(token_for(admin)),
        )
        assert detail.status_code == 200
        payload = detail.json()
        assert payload['reported_version'] == 1
        assert payload['post_version'] == 2
        assert json.loads(payload['evidence']) == {
            'title': 'First title',
            'body': 'First body, kept only as report evidence.',
        }


def test_platform_hide_blocks_owner_edit_and_public_read_bypass(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    reporter = make_user()
    admin = make_user(platform_admin=True)
    receipt = submit_report(client, announcement['id'], reporter, token_for).json()

    hidden = client.post(
        f"/api/v1/moderation/announcement-reports/{receipt['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '"1"'},
        json={'action': 'hide'},
    )
    assert hidden.status_code == 200
    assert hidden.json()['status'] == 'hidden'
    assert hidden.json()['post_state'] == 'hidden'
    assert hidden.json()['post_version'] == 2
    assert hidden.json()['evidence'] is None

    owner_edit = client.patch(
        f"/api/v1/announcements/{announcement['id']}",
        headers=auth(token_for(owner)) | {'If-Match': '"2"'},
        json={'body': 'An edit must not bypass platform hiding.'},
    )
    assert owner_edit.status_code == 409
    assert 'body' not in owner_edit.json()

    unreadable = client.get(
        f"/api/v1/announcements/{announcement['id']}",
        headers=auth(token_for(reporter)),
    )
    assert unreadable.status_code == 404
    detail = client.get(
        f"/api/v1/moderation/announcement-reports/{receipt['id']}",
        headers=auth(token_for(admin)),
    )
    assert detail.status_code == 200
    assert detail.json()['post_state'] == 'hidden'
    assert detail.json()['evidence'] is None
    assert count_rows(
        db,
        AnnouncementRevision,
        AnnouncementRevision.announcement_id == announcement['id'],
        AnnouncementRevision.version == 2,
        AnnouncementRevision.action == 'hide',
    ) == 1


def test_expiry_purges_evidence_and_does_not_reconstruct_it_from_revisions(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    reporter = make_user()
    admin = make_user(platform_admin=True)
    receipt = submit_report(client, announcement['id'], reporter, token_for).json()
    report = db.get(AnnouncementReport, receipt['id'])
    boundary = now()
    report.deadline = boundary
    db.commit()

    at_boundary = get_announcement_moderation_report(
        db, actor_for(admin), receipt['id'], at=boundary
    )
    assert at_boundary['status'] == 'open'
    assert at_boundary['evidence'] is None

    get_organization(db, organization.id, lock=True)
    assert catch_up_announcement_reports_locked(db, organization.id, boundary) == 1
    db.commit()
    db.refresh(report)
    assert report.status == 'expired'
    assert report.evidence is None
    expiry_decision = db.scalar(
        select(AnnouncementReportDecision).where(
            AnnouncementReportDecision.report_id == report.id,
            AnnouncementReportDecision.action == 'expire',
        )
    )
    assert expiry_decision is not None
    assert expiry_decision.reviewer_id is None

    after_expiry = get_announcement_moderation_report(
        db, actor_for(admin), receipt['id'], at=boundary + timedelta(days=1)
    )
    assert after_expiry['evidence'] is None
    revision = db.scalar(
        select(AnnouncementRevision).where(
            AnnouncementRevision.announcement_id == announcement['id'],
            AnnouncementRevision.version == 1,
        )
    )
    assert revision is not None and revision.body == 'Original body'


def test_only_originating_hide_case_can_restore_an_announcement(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    first_reporter = make_user()
    second_reporter = make_user()
    admin = make_user(platform_admin=True)
    first = submit_report(client, announcement['id'], first_reporter, token_for).json()
    second = submit_report(client, announcement['id'], second_reporter, token_for).json()

    missing_version = client.post(
        f"/api/v1/moderation/announcement-reports/{first['id']}/decision",
        headers=auth(token_for(admin)),
        json={'action': 'hide'},
    )
    malformed_version = client.post(
        f"/api/v1/moderation/announcement-reports/{first['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '1'},
        json={'action': 'hide'},
    )
    stale_version = client.post(
        f"/api/v1/moderation/announcement-reports/{first['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '"2"'},
        json={'action': 'hide'},
    )
    assert missing_version.status_code == 409
    assert malformed_version.status_code == 409
    assert stale_version.status_code == 409
    assert count_rows(db, AnnouncementReportDecision) == 0

    first_hide = client.post(
        f"/api/v1/moderation/announcement-reports/{first['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '"1"'},
        json={'action': 'hide'},
    )
    assert first_hide.status_code == 200
    assert first_hide.headers['etag'] == '"2"'
    assert first_hide.json()['status'] == 'hidden'

    other_hide = client.post(
        f"/api/v1/moderation/announcement-reports/{second['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '"2"'},
        json={'action': 'hide'},
    )
    assert other_hide.status_code == 409
    second_restore = client.post(
        f"/api/v1/moderation/announcement-reports/{second['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '"2"'},
        json={'action': 'restore'},
    )
    assert second_restore.status_code == 409
    assert count_rows(
        db,
        AnnouncementReportDecision,
        AnnouncementReportDecision.report_id == second['id'],
    ) == 0

    same_case_hide_retry = client.post(
        f"/api/v1/moderation/announcement-reports/{first['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '"1"'},
        json={'action': 'hide'},
    )
    assert same_case_hide_retry.status_code == 200
    assert count_rows(
        db,
        AnnouncementReportDecision,
        AnnouncementReportDecision.report_id == first['id'],
    ) == 1

    originating_restore = client.post(
        f"/api/v1/moderation/announcement-reports/{first['id']}/decision",
        headers=auth(token_for(admin)) | {'If-Match': '"2"'},
        json={'action': 'restore'},
    )
    assert originating_restore.status_code == 200
    assert originating_restore.json()['status'] == 'restored'
    assert originating_restore.json()['post_state'] == 'visible'
    second_detail = client.get(
        f"/api/v1/moderation/announcement-reports/{second['id']}",
        headers=auth(token_for(admin)),
    )
    assert second_detail.status_code == 200
    assert second_detail.json()['status'] == 'open'
    assert second_detail.json()['post_state'] == 'visible'


def test_hidden_case_can_be_restored_after_evidence_deadline_with_idempotent_retries(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    reporter = make_user()
    admin = make_user(platform_admin=True)
    receipt = submit_report(client, announcement['id'], reporter, token_for).json()
    report = db.get(AnnouncementReport, receipt['id'])
    deadline = report.deadline

    hide_at = deadline - timedelta(seconds=1)
    hidden = decide_announcement_report(
        db, actor_for(admin), report.id, 'hide', expected_version=1, at=hide_at
    )
    db.commit()
    assert hidden['status'] == 'hidden'
    assert hidden['evidence'] is None

    before_retry = (
        count_rows(db, AnnouncementReportDecision, AnnouncementReportDecision.report_id == report.id),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )
    hide_retry = decide_announcement_report(
        db, actor_for(admin), report.id, 'hide', expected_version=1, at=deadline
    )
    assert hide_retry['status'] == 'hidden'
    assert before_retry == (
        count_rows(db, AnnouncementReportDecision, AnnouncementReportDecision.report_id == report.id),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )

    restored = decide_announcement_report(
        db, actor_for(admin), report.id, 'restore', expected_version=2,
        at=deadline + timedelta(days=1),
    )
    db.commit()
    assert restored['status'] == 'restored'
    assert restored['post_state'] == 'visible'
    assert restored['post_version'] == 3
    assert restored['evidence'] is None

    before_restore_retry = (
        count_rows(db, AnnouncementReportDecision, AnnouncementReportDecision.report_id == report.id),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )
    restore_retry = decide_announcement_report(
        db, actor_for(admin), report.id, 'restore', expected_version=2,
        at=deadline + timedelta(days=2),
    )
    assert restore_retry['status'] == 'restored'
    assert before_restore_retry == (
        count_rows(db, AnnouncementReportDecision, AnnouncementReportDecision.report_id == report.id),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )
    actions = list(db.scalars(
        select(AnnouncementReportDecision.action)
        .where(AnnouncementReportDecision.report_id == report.id)
        .order_by(AnnouncementReportDecision.created_at, AnnouncementReportDecision.id)
    ))
    assert actions == ['hide', 'restore']


def test_same_action_retries_do_not_duplicate_decisions_revisions_or_notices(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    reporters = [make_user() for _ in range(3)]
    admin = make_user(platform_admin=True)
    reports = [submit_report(client, announcement['id'], reporter, token_for).json() for reporter in reporters]

    def apply(report_id, action, version=None):
        headers = auth(token_for(admin))
        if version is not None:
            headers['If-Match'] = f'"{version}"'
        return client.post(
            f'/api/v1/moderation/announcement-reports/{report_id}/decision',
            headers=headers,
            json={'action': action},
        )

    hide = apply(reports[0]['id'], 'hide', 1)
    assert hide.status_code == 200
    counts_after_hide = (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )
    assert apply(reports[0]['id'], 'hide', 1).status_code == 200
    assert counts_after_hide == (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )

    restore = apply(reports[0]['id'], 'restore', 2)
    assert restore.status_code == 200
    counts_after_restore = (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )
    assert apply(reports[0]['id'], 'restore', 2).status_code == 200
    assert counts_after_restore == (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )

    remove = apply(reports[1]['id'], 'remove', 3)
    assert remove.status_code == 200
    counts_after_remove = (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )
    assert apply(reports[1]['id'], 'remove', 3).status_code == 200
    assert counts_after_remove == (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )

    dismiss = apply(reports[2]['id'], 'dismiss')
    assert dismiss.status_code == 200
    counts_after_dismiss = (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )
    assert apply(reports[2]['id'], 'dismiss').status_code == 200
    assert counts_after_dismiss == (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )


def test_non_platform_users_cannot_read_or_decide_announcement_reports(
    client, db, make_user, make_org, token_for
):
    owner = make_user()
    organization = make_org(owner=owner)
    announcement = publish_announcement(client, organization, owner, token_for)
    reporter = make_user()
    make_user(platform_admin=True)
    receipt = submit_report(client, announcement['id'], reporter, token_for).json()
    before = (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )

    queue = client.get('/api/v1/moderation/announcement-reports', headers=auth(token_for(owner)))
    detail = client.get(
        f"/api/v1/moderation/announcement-reports/{receipt['id']}",
        headers=auth(token_for(owner)),
    )
    decision = client.post(
        f"/api/v1/moderation/announcement-reports/{receipt['id']}/decision",
        headers=auth(token_for(owner)) | {'If-Match': '"1"'},
        json={'action': 'hide'},
    )
    assert queue.status_code == detail.status_code == decision.status_code == 403
    assert before == (
        count_rows(db, AnnouncementReportDecision),
        count_rows(db, AnnouncementRevision, AnnouncementRevision.announcement_id == announcement['id']),
        count_rows(db, Notification, Notification.org_id == organization.id, Notification.kind == 'safety_report'),
    )


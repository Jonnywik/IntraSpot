from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import uuid4

from sqlalchemy import func, select, update

from app.db.models import now, uid
from app.db.session import session_factory
from app.domains.identity.models import User
from app.domains.memberships import applications, policy
from app.domains.memberships.models import MembershipApplication, MembershipAudit, MembershipInvitation
from app.domains.organizations.models import OrgMembership


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def submit_application(client, org_id, token, *, client_key=None, persona_shared=None, **extra):
    payload = {'client_key': client_key or str(uuid4())}
    if persona_shared is not None:
        payload['persona_shared'] = persona_shared
    payload.update(extra)
    return client.post(
        f'/api/v1/organizations/{org_id}/membership-applications',
        json=payload,
        headers=auth(token),
    )


def test_guest_can_submit_and_only_owner_can_read_or_withdraw_application(
    client, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    guest = make_user(email='fictional-membership-guest@example.test')
    other = make_user()
    key = str(uuid4())
    url = f'/api/v1/organizations/{org.id}/membership-applications'

    anonymous = client.post(url, json={'client_key': str(uuid4())})
    submitted = client.post(
        url,
        json={'client_key': key},
        headers=auth(token_for(guest)),
    )
    own_list = client.get('/api/v1/me/membership-applications', headers=auth(token_for(guest)))
    other_list = client.get('/api/v1/me/membership-applications', headers=auth(token_for(other)))
    foreign_withdrawal = client.post(
        f"/api/v1/membership-applications/{submitted.json()['id']}/withdraw",
        headers=auth(token_for(other)),
    )

    assert anonymous.status_code == 401
    assert submitted.status_code == 200
    assert submitted.json()['status'] == 'pending'
    assert submitted.json()['persona_shared'] is False
    assert own_list.status_code == 200 and [row['id'] for row in own_list.json()] == [submitted.json()['id']]
    assert other_list.status_code == 200 and other_list.json() == []
    assert foreign_withdrawal.status_code == 404


def test_application_consent_is_strict_and_input_forbids_freeform_note(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    applicant = make_user()

    invalid_consent = [
        submit_application(client, org.id, token_for(applicant), persona_shared=value)
        for value in ('true', 1)
    ]
    extra_note = submit_application(
        client,
        org.id,
        token_for(applicant),
        persona_shared=False,
        note='Please make an exception for me.',
    )

    assert all(response.status_code == 422 for response in invalid_consent)
    assert all(response.json()['error']['code'] == 'validation_error' for response in invalid_consent)
    assert extra_note.status_code == 422
    assert extra_note.json()['error']['code'] == 'validation_error'
    assert db.scalar(select(func.count(MembershipApplication.id))) == 0


def test_approval_before_eligibility_unlocks_only_after_trusted_user_update(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    applicant = make_user(email='fictional-pre-eligibility@example.test')
    owner_headers = auth(token_for(owner))
    applicant_headers = auth(token_for(applicant))
    submitted = submit_application(client, org.id, token_for(applicant))

    approved = client.post(
        f"/api/v1/organizations/{org.id}/membership-applications/{submitted.json()['id']}/decision",
        json={'outcome': 'approved'},
        headers=owner_headers,
    )
    grant = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org.id,
        OrgMembership.user_id == applicant.id,
    ))
    db.execute(
        update(User)
        .where(User.id == applicant.id)
        .values(email=f'fictional-unlocked-{uuid4()}@students.plm.edu.ph', email_verified=True)
    )
    db.commit()
    after_trusted_update = client.get(
        '/api/v1/me/membership-applications',
        headers=applicant_headers,
    )

    assert approved.status_code == 200
    assert approved.json()['status'] == 'approved'
    assert approved.json()['access_ready'] is False
    assert grant is not None and grant.role == 'member' and grant.active is True
    assert after_trusted_update.status_code == 200
    assert after_trusted_update.json()[0]['access_ready'] is True


def test_application_key_retry_conflicts_and_duplicate_pending_are_controlled(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    other_owner = make_user()
    other_org = make_org(owner=other_owner)
    applicant = make_user()
    key = str(uuid4())
    applicant_token = token_for(applicant)

    first = submit_application(client, org.id, applicant_token, client_key=key, persona_shared=False)
    retry = submit_application(client, org.id, applicant_token, client_key=key, persona_shared=False)
    changed_consent = submit_application(client, org.id, applicant_token, client_key=key, persona_shared=True)
    changed_org = submit_application(client, other_org.id, applicant_token, client_key=key, persona_shared=False)
    duplicate_pending = submit_application(client, org.id, applicant_token, persona_shared=False)

    assert first.status_code == retry.status_code == 200
    assert retry.json()['id'] == first.json()['id']
    assert changed_consent.status_code == changed_org.status_code == 409
    assert changed_consent.json()['error']['code'] == 'membership_key_reused'
    assert changed_org.json()['error']['code'] == 'membership_key_reused'
    assert duplicate_pending.status_code == 409
    assert duplicate_pending.json()['error']['code'] == 'membership_application_pending'
    assert db.scalar(select(func.count(MembershipApplication.id))) == 1


def test_rejected_application_can_be_reapplied_immediately(client, make_user, make_org, token_for):
    owner = make_user()
    org = make_org(owner=owner)
    applicant = make_user()
    owner_headers = auth(token_for(owner))
    first = submit_application(client, org.id, token_for(applicant))

    rejected = client.post(
        f"/api/v1/organizations/{org.id}/membership-applications/{first.json()['id']}/decision",
        json={'outcome': 'rejected', 'reason': 'requirements_not_met'},
        headers=owner_headers,
    )
    reapplied = submit_application(client, org.id, token_for(applicant))

    assert rejected.status_code == 200 and rejected.json()['status'] == 'rejected'
    assert reapplied.status_code == 200 and reapplied.json()['status'] == 'pending'
    assert reapplied.json()['id'] != first.json()['id']


def test_withdrawal_retry_and_exact_24_hour_reapplication_boundary(
    client, monkeypatch, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    applicant = make_user()
    applicant_token = token_for(applicant)
    start = now()
    monkeypatch.setattr(applications, 'now', lambda: start)
    submitted = submit_application(client, org.id, applicant_token)
    application_id = submitted.json()['id']

    withdrawn_at = start + timedelta(minutes=5)
    monkeypatch.setattr(applications, 'now', lambda: withdrawn_at)
    withdrawn = client.post(
        f'/api/v1/membership-applications/{application_id}/withdraw',
        headers=auth(applicant_token),
    )
    retry_at = withdrawn_at + timedelta(minutes=1)
    monkeypatch.setattr(applications, 'now', lambda: retry_at)
    withdrawal_retry = client.post(
        f'/api/v1/membership-applications/{application_id}/withdraw',
        headers=auth(applicant_token),
    )
    before_boundary = withdrawn_at + timedelta(hours=24) - timedelta(microseconds=1)
    monkeypatch.setattr(applications, 'now', lambda: before_boundary)
    too_early = submit_application(client, org.id, applicant_token)
    boundary = withdrawn_at + timedelta(hours=24)
    monkeypatch.setattr(applications, 'now', lambda: boundary)
    allowed = submit_application(client, org.id, applicant_token)

    assert withdrawn.status_code == 200 and withdrawn.json()['status'] == 'withdrawn'
    assert withdrawal_retry.status_code == 200
    assert withdrawal_retry.json()['resolved_at'] == withdrawn.json()['resolved_at']
    assert datetime.fromisoformat(withdrawn.json()['can_reapply_at']) == boundary
    assert too_early.status_code == 409
    assert too_early.json()['error']['code'] == 'membership_withdrawal_cooldown'
    assert allowed.status_code == 200 and allowed.json()['status'] == 'pending'


def test_application_persona_is_separate_opt_in_and_hidden_after_closure(
    client, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    private_applicant = make_user(
        email='fictional-private-persona@example.test',
        nickname='PRIVATE GLOBAL NICKNAME',
        age_bracket='18-24',
        tags=['ceramics'],
        pronouns='they/them',
        icebreaker='PRIVATE PROFILE ICEBREAKER',
        persona_visible=True,
    )
    opted_in = make_user(
        email='fictional-opted-in@example.test',
        nickname='CONSENTED NICKNAME',
        age_bracket='18-24',
        tags=['music'],
        pronouns='she/her',
        icebreaker='PRIVATE OPT-IN ICEBREAKER',
        persona_visible=False,
    )
    private_request = submit_application(client, org.id, token_for(private_applicant))
    shared_request = submit_application(
        client,
        org.id,
        token_for(opted_in),
        persona_shared=True,
    )

    review = client.get(
        f'/api/v1/organizations/{org.id}/membership-applications',
        headers=auth(token_for(owner)),
    )
    private_row = next(row for row in review.json() if row['user_id'] == private_applicant.id)
    shared_row = next(row for row in review.json() if row['user_id'] == opted_in.id)
    closed = client.post(
        f"/api/v1/organizations/{org.id}/membership-applications/{shared_request.json()['id']}/decision",
        json={'outcome': 'rejected', 'reason': 'other'},
        headers=auth(token_for(owner)),
    )

    assert private_request.status_code == shared_request.status_code == review.status_code == 200
    assert private_row['applicant_label'] == 'Applicant' and private_row['persona'] is None
    assert shared_row['applicant_label'] == 'CONSENTED NICKNAME'
    assert shared_row['persona'] == {'nickname': 'CONSENTED NICKNAME', 'tags': ['music']}
    assert private_applicant.nickname not in review.text
    assert private_applicant.email not in review.text
    assert opted_in.email not in review.text
    assert '18-24' not in review.text and 'she/her' not in review.text
    assert 'PRIVATE PROFILE ICEBREAKER' not in review.text
    assert 'PRIVATE OPT-IN ICEBREAKER' not in review.text
    assert closed.status_code == 200
    assert closed.json()['applicant_label'] == 'Applicant' and closed.json()['persona'] is None


def test_invitation_create_retry_and_concurrent_same_key_deduplicate(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    recipient = make_user()
    key = str(uuid4())
    barrier = Barrier(2)

    def create_concurrently():
        with session_factory()() as session:
            barrier.wait(timeout=15)
            with session.begin():
                return applications.create_invitation(
                    session,
                    owner.id,
                    org.id,
                    recipient.id,
                    key,
                )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [future.result(timeout=30) for future in (
            pool.submit(create_concurrently),
            pool.submit(create_concurrently),
        )]

    retry = client.post(
        f'/api/v1/organizations/{org.id}/membership-invitations',
        json={'recipient_id': recipient.id, 'client_key': key},
        headers=auth(token_for(owner)),
    )
    conflict = client.post(
        f'/api/v1/organizations/{org.id}/membership-invitations',
        json={'recipient_id': make_user().id, 'client_key': key},
        headers=auth(token_for(owner)),
    )

    assert first['id'] == second['id']
    assert retry.status_code == 200 and retry.json()['id'] == first['id']
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'membership_key_reused'
    assert db.scalar(select(func.count(MembershipInvitation.id)).where(
        MembershipInvitation.sender_id == owner.id,
        MembershipInvitation.client_key == key,
    )) == 1


def test_invitation_is_recipient_bound_and_accepted_retry_does_not_regrant(
    client, db, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    recipient = make_user(email='fictional-ineligible-recipient@example.test')
    stranger = make_user()
    grant = OrgMembership(
        id=uid(), org_id=org.id, user_id=recipient.id, role='admin', active=False,
    )
    db.add(grant)
    db.commit()
    created = client.post(
        f'/api/v1/organizations/{org.id}/membership-invitations',
        json={'recipient_id': recipient.id, 'client_key': str(uuid4())},
        headers=auth(token_for(owner)),
    )
    invitation_id = created.json()['id']
    stranger_accept = client.post(
        f'/api/v1/membership-invitations/{invitation_id}/accept',
        headers=auth(token_for(stranger)),
    )
    own_invitations = client.get(
        '/api/v1/me/membership-invitations',
        headers=auth(token_for(recipient)),
    )
    accepted = client.post(
        f'/api/v1/membership-invitations/{invitation_id}/accept',
        headers=auth(token_for(recipient)),
    )
    db.refresh(grant)
    grant.active = False
    db.commit()
    retry = client.post(
        f'/api/v1/membership-invitations/{invitation_id}/accept',
        headers=auth(token_for(recipient)),
    )
    db.refresh(grant)

    assert created.status_code == 200
    assert stranger_accept.status_code == 404
    assert own_invitations.status_code == 200
    assert [row['id'] for row in own_invitations.json()] == [invitation_id]
    assert accepted.status_code == 200 and accepted.json()['status'] == 'accepted'
    assert accepted.json()['access_ready'] is False
    assert grant.role == 'member' and grant.active is False
    assert retry.status_code == 200 and retry.json()['status'] == 'accepted'
    assert grant.active is False
    assert db.scalar(select(func.count(MembershipAudit.id)).where(
        MembershipAudit.org_id == org.id,
        MembershipAudit.user_id == recipient.id,
        MembershipAudit.action == 'membership_granted',
    )) == 1


def test_expired_actions_409_read_projection_and_worker_catchup_then_revocation(
    client, db, monkeypatch, make_user, make_org, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    recipient = make_user()
    recipient_token = token_for(recipient)
    created = client.post(
        f'/api/v1/organizations/{org.id}/membership-invitations',
        json={'recipient_id': recipient.id, 'client_key': str(uuid4())},
        headers=auth(token_for(owner)),
    )
    invitation = db.get(MembershipInvitation, created.json()['id'])
    expiry = invitation.expires_at
    monkeypatch.setattr(applications, 'now', lambda: expiry)

    projection = client.get('/api/v1/me/membership-invitations', headers=auth(recipient_token))
    accept_expired = client.post(
        f"/api/v1/membership-invitations/{invitation.id}/accept",
        headers=auth(recipient_token),
    )
    decline_expired = client.post(
        f"/api/v1/membership-invitations/{invitation.id}/decline",
        headers=auth(recipient_token),
    )
    db.refresh(invitation)
    policy.get_org(db, org.id, lock=True, approved=True)
    changed = applications.catch_up_invitations_locked(db, org.id, expiry)
    db.commit()
    db.refresh(invitation)
    policy.get_org(db, org.id, lock=True, approved=True)
    unchanged = applications.catch_up_invitations_locked(db, org.id, expiry)
    db.commit()
    monkeypatch.setattr(applications, 'now', now)

    revoke_recipient = make_user()
    revoke_created = client.post(
        f'/api/v1/organizations/{org.id}/membership-invitations',
        json={'recipient_id': revoke_recipient.id, 'client_key': str(uuid4())},
        headers=auth(token_for(owner)),
    )
    revoked = client.post(
        f"/api/v1/organizations/{org.id}/membership-invitations/{revoke_created.json()['id']}/revoke",
        headers=auth(token_for(owner)),
    )
    accept_revoked = client.post(
        f"/api/v1/membership-invitations/{revoke_created.json()['id']}/accept",
        headers=auth(token_for(revoke_recipient)),
    )

    projected = next(row for row in projection.json() if row['id'] == invitation.id)
    assert created.status_code == 200 and projected['status'] == 'expired'
    assert accept_expired.status_code == decline_expired.status_code == 409
    assert accept_expired.json()['error']['code'] == 'membership_invitation_expired'
    assert decline_expired.json()['error']['code'] == 'membership_invitation_expired'
    assert invitation.status == 'expired' and changed == 1 and unchanged == 0
    assert revoked.status_code == 200 and revoked.json()['status'] == 'revoked'
    assert accept_revoked.status_code == 409
    assert accept_revoked.json()['error']['code'] == 'membership_invitation_closed'


def test_lifecycle_notice_kinds_use_generic_messages_and_org_context(monkeypatch):
    delivered = []
    messages = {
        'membership_left': 'You have left the organization.',
        'membership_removed': 'Your organization membership was removed.',
        'membership_role_changed': 'Your organization membership role was updated.',
    }

    def capture(db, **payload):
        delivered.append((db, payload))

    monkeypatch.setattr('app.notifications.notify_in_app', capture)
    db = object()
    for kind, message in messages.items():
        delivered.clear()
        policy.notice(db, 'fictional-org-id', 'fictional-user-id', kind, 'immutable-operation-id')
        assert delivered == [(db, {
            'user_id': 'fictional-user-id',
            'org_id': 'fictional-org-id',
            'kind': kind,
            'message': message,
            'dedupe_key': 'immutable-operation-id',
        })]

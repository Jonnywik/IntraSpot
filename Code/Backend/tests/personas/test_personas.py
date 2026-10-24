from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.communication_schemas import ContentCreate
from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.chat import service as chat_service
from app.domains.identity.service import actor_for_user
from app.domains.memberships import applications as membership_applications
from app.domains.memberships.models import EventAccessRevocation, MembershipApplication
from app.domains.moderation.models import ContentHide
from app.domains.personas import service as persona_service
from app.domains.personas.models import EventPersonaVisibility, UserBlock
from app.domains.registrations.models import Registration
from app.domains.social import service as social_service
from app.domains.social.models import EventComment


def _register(db, event, user, *, status='confirmed', persona_shared=False):
    order = db.scalar(select(func.count(Registration.id)).where(
        Registration.event_id == event.id,
    )) or 0
    registration = Registration(
        id=uid(),
        user_id=user.id,
        event_id=event.id,
        status=status,
        admission_order=order + 1,
        persona_shared=persona_shared,
    )
    db.add(registration)
    db.commit()
    return registration


def _comment(db, event, author, body='Fictional public comment'):
    return social_service.create_comment(
        db,
        event.id,
        author.id,
        ContentCreate(body=body, client_key=uuid4()),
        at=now(),
    )


def _message(db, event, author, body='Fictional chat message'):
    return chat_service.send_chat_message(
        db,
        event.id,
        author.id,
        ContentCreate(body=body, client_key=uuid4()),
        at=now(),
    )


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_block_helpers_are_mutual_but_warning_and_list_projections_are_outgoing_only(
    db, make_user,
):
    viewer = make_user()
    outgoing = make_user()
    incoming = make_user()
    db.add_all([
        UserBlock(blocker_id=viewer.id, target_id=outgoing.id),
        UserBlock(blocker_id=incoming.id, target_id=viewer.id),
    ])
    db.commit()

    assert persona_service.blocked_user_ids(db, viewer.id) == {outgoing.id, incoming.id}
    assert persona_service.is_blocked(db, viewer.id, outgoing.id)
    assert persona_service.is_blocked(db, viewer.id, incoming.id)
    assert persona_service.outgoing_blocked_user_ids(db, viewer.id) == {outgoing.id}

    listed = persona_service.list_blocks(db, viewer.id)
    assert [row.model_dump() for row in listed] == [
        {'user_id': outgoing.id, 'created_at': listed[0].created_at},
    ]
    assert set(listed[0].model_dump()) == {'user_id', 'created_at'}
    assert incoming.id not in {row.user_id for row in listed}


@pytest.mark.parametrize('block_direction', ['reviewer_blocks_applicant', 'applicant_blocks_reviewer'])
def test_block_in_either_direction_masks_reviewer_consent_only_projection(
    db, make_user, make_org, block_direction,
):
    reviewer = make_user()
    applicant = make_user(nickname='Consent-only applicant', tags=['arts'])
    organization = make_org(owner=reviewer)
    application = MembershipApplication(
        id=uid(),
        org_id=organization.id,
        user_id=applicant.id,
        client_key=str(uuid4()),
        persona_shared=True,
    )
    if block_direction == 'reviewer_blocks_applicant':
        block = UserBlock(blocker_id=reviewer.id, target_id=applicant.id)
    else:
        block = UserBlock(blocker_id=applicant.id, target_id=reviewer.id)
    db.add_all([application, block])
    db.commit()

    projection = membership_applications._application_review(db, application, now(), reviewer.id)
    assert projection['applicant_label'] == 'Applicant'
    assert projection['persona'] is None
    assert projection['user_id'] == applicant.id


def test_visibility_api_requires_strict_boolean_and_sharing_expires_at_event_end(
    client, db, make_user, make_event, token_for,
):
    attendee = make_user()
    event = make_event()
    _register(db, event, attendee)
    url = f'/api/v1/events/{event.id}/persona-visibility'
    headers = _auth(token_for(attendee))

    for invalid in ('true', 1, None):
        response = client.put(url, json={'visible': invalid}, headers=headers)
        assert response.status_code == 422

    enabled = client.put(url, json={'visible': True}, headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()['visible'] is True
    assert set(enabled.json()) == {'visible', 'expires_at'}
    assert client.get(url, headers=headers).json()['visible'] is True
    assert persona_service.get_event_visibility(db, event.id, attendee.id, at=event.ends_at).visible is False
    with pytest.raises(DomainError) as expired:
        persona_service.set_event_visibility(db, event.id, attendee.id, True, at=event.ends_at)
    assert expired.value.status == 409

    non_attendee = make_user()
    with pytest.raises(DomainError) as forbidden:
        persona_service.get_event_visibility(db, event.id, non_attendee.id)
    assert forbidden.value.status == 403


def test_global_text_persona_is_available_from_shared_chat_without_comment_but_reviewer_consent_is_not(
    db, make_user, make_event,
):
    viewer = make_user(nickname='Fictional viewer')
    global_author = make_user(nickname='Globally shared', persona_visible=True)
    scoped_author = make_user(nickname='Event-only share', persona_visible=False)
    event = make_event()
    _register(db, event, viewer)
    _register(db, event, global_author)
    _register(db, event, scoped_author, persona_shared=True)

    _message(db, event, global_author, 'Global author message')
    _message(db, event, scoped_author, 'Scoped author message')
    db.add(EventPersonaVisibility(event_id=event.id, user_id=scoped_author.id, visible=True))
    db.commit()

    global_profile = persona_service.get_event_persona(db, event.id, global_author.id, viewer.id)
    scoped_profile = persona_service.get_event_persona(db, event.id, scoped_author.id, viewer.id)
    assert global_profile.nickname == 'Globally shared'
    assert scoped_profile.nickname == 'Event-only share'
    assert set(global_profile.model_dump()) == {'nickname', 'age_bracket', 'tags', 'pronouns', 'icebreaker'}

    thread = chat_service.get_chat_thread(db, event.id, viewer.id)
    labels = {item.body: item.author_label for item in thread.items}
    assert labels['Global author message'] == 'Globally shared'
    assert labels['Scoped author message'] == 'Event-only share'
    assert all(item.body is not None for item in thread.items)

    # Registration.persona_shared remains reviewer-only; without either global
    # or event-specific consent it must not make chat/profile labels visible.
    private_author = make_user(nickname='Reviewer-only', persona_visible=False)
    _register(db, event, private_author, persona_shared=True)
    _message(db, event, private_author, 'Reviewer-only message')
    with pytest.raises(DomainError) as unavailable:
        persona_service.get_event_persona(db, event.id, private_author.id, viewer.id)
    assert (unavailable.value.status, unavailable.value.code) == (404, 'persona_unavailable')
    thread = chat_service.get_chat_thread(db, event.id, viewer.id)
    private_item = next(item for item in thread.items if item.body == 'Reviewer-only message')
    assert private_item.author_label == 'PLM member'
    assert private_item.body == 'Reviewer-only message'


def test_event_only_visibility_requires_unrevoked_attendance_and_stops_after_event_end(
    db, make_user, make_event,
):
    viewer = make_user()
    target = make_user(nickname='Temporary event share', persona_visible=False)
    event = make_event()
    _register(db, event, viewer)
    target_registration = _register(db, event, target)
    _message(db, event, target)
    db.add(EventPersonaVisibility(event_id=event.id, user_id=target.id, visible=True))
    db.commit()

    assert persona_service.get_event_persona(db, event.id, target.id, viewer.id).nickname == 'Temporary event share'
    db.add(EventAccessRevocation(
        id=uid(),
        event_id=event.id,
        user_id=target.id,
        cutoff_order=target_registration.admission_order,
    ))
    db.commit()
    with pytest.raises(DomainError) as revoked:
        persona_service.get_event_persona(db, event.id, target.id, viewer.id)
    assert (revoked.value.status, revoked.value.code) == (404, 'persona_unavailable')

    # Even retained chat context cannot extend event-only consent past ends_at.
    db.delete(db.get(EventAccessRevocation, db.scalar(select(EventAccessRevocation.id))))
    db.commit()
    with pytest.raises(DomainError) as ended:
        persona_service.get_event_persona(db, event.id, target.id, viewer.id, at=event.ends_at)
    assert (ended.value.status, ended.value.code) == (404, 'persona_unavailable')


def test_global_comment_labels_require_eligible_viewer_and_hide_pending_approval_persona(
    db, make_user, make_event,
):
    author = make_user(nickname='Broad text share', persona_visible=True)
    viewer = make_user()
    event = make_event()
    _comment(db, event, author)

    guest_page = social_service.list_comments(db, event.id, None)
    eligible_page = social_service.list_comments(db, event.id, actor_for_user(db, viewer))
    guest_item = guest_page.items[0]
    eligible_item = eligible_page.items[0]
    assert guest_item.author_label == 'PLM member'
    assert eligible_item.author_label == 'Broad text share'
    assert guest_page.author_labels == {}
    assert eligible_page.author_labels == {author.id: 'Broad text share'}

    other_author = make_user(nickname='Private label')
    _comment(db, event, other_author, 'Second comment')
    limited_page = social_service.list_comments(
        db, event.id, actor_for_user(db, viewer), limit=1,
    )
    assert len(limited_page.items) == 1
    assert set(limited_page.author_labels) == {author.id, other_author.id}
    assert limited_page.author_labels == {
        author.id: 'Broad text share',
        other_author.id: 'PLM member',
    }

    pending_author = make_user(nickname='Pending applicant', persona_visible=True)
    approval_event = make_event(registration_mode='approval', review_window_minutes=60)
    _register(db, approval_event, pending_author, status='pending')
    _comment(db, approval_event, pending_author, 'Pending approval comment')
    pending_page = social_service.list_comments(
        db, approval_event.id, actor_for_user(db, viewer),
    )
    pending_item = pending_page.items[0]
    assert pending_item.body == 'Pending approval comment'
    assert pending_item.author_label == 'PLM member'
    assert pending_page.author_labels[pending_author.id] == 'PLM member'


def test_block_endpoint_requires_real_context_is_idempotent_and_keeps_content_access(
    client, db, make_user, make_event, token_for,
):
    viewer = make_user(nickname='Fictional viewer')
    target = make_user(nickname='Blocked but visible', persona_visible=True)
    incoming_blocker = make_user()
    event = make_event()
    _register(db, event, viewer)
    _register(db, event, target)
    comment = _comment(db, event, target)
    _message(db, event, target, 'Chat body remains readable')
    headers = _auth(token_for(viewer))
    block_url = f'/api/v1/events/{event.id}/blocks/{target.id}'

    first = client.put(block_url, headers=headers)
    retry = client.put(block_url, headers=headers)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert set(first.json()) == {'user_id', 'created_at'}
    assert first.json()['user_id'] == target.id
    assert db.scalar(select(func.count(UserBlock.target_id)).where(
        UserBlock.blocker_id == viewer.id,
        UserBlock.target_id == target.id,
    )) == 1

    db.add(UserBlock(blocker_id=incoming_blocker.id, target_id=viewer.id))
    db.commit()
    listed = client.get('/api/v1/me/blocks', headers=headers)
    assert listed.status_code == 200
    assert listed.json() == [first.json()]
    assert set(listed.json()[0]) == {'user_id', 'created_at'}
    assert incoming_blocker.id not in listed.text

    unknown_context = make_user()
    denied = client.put(f'/api/v1/events/{event.id}/blocks/{unknown_context.id}', headers=headers)
    assert denied.status_code == 404
    unknown_persona = client.get(
        f'/api/v1/events/{event.id}/personas/{unknown_context.id}', headers=headers,
    )
    missing_persona = client.get(
        f'/api/v1/events/{event.id}/personas/{uuid4()}', headers=headers,
    )
    assert unknown_persona.status_code == missing_persona.status_code == 404
    assert unknown_persona.json()['error'] == missing_persona.json()['error']
    self_block = client.put(f'/api/v1/events/{event.id}/blocks/{viewer.id}', headers=headers)
    assert self_block.status_code == 422

    unavailable = client.get(f'/api/v1/events/{event.id}/personas/{target.id}', headers=headers)
    assert unavailable.status_code == 404
    assert unavailable.json()['error'] == {
        'code': 'persona_unavailable',
        'message': 'This persona is unavailable in this event.',
    }

    comments = social_service.list_comments(db, event.id, actor_for_user(db, viewer))
    assert comments.items[0].id == comment.id
    assert comments.items[0].body == 'Fictional public comment'
    assert comments.items[0].author_label == 'PLM member'
    thread = chat_service.get_chat_thread(db, event.id, viewer.id)
    chat_item = next(item for item in thread.items if item.body == 'Chat body remains readable')
    assert chat_item.body == 'Chat body remains readable'
    assert chat_item.author_label == 'PLM member'
    assert thread.author_labels[target.id] == 'PLM member'

    blocked_poll = chat_service.get_chat_thread(
        db, event.id, viewer.id, after_sequence=chat_item.sequence,
    )
    assert blocked_poll.items == []
    assert blocked_poll.author_labels[target.id] == 'PLM member'

    assert client.delete(f'/api/v1/me/blocks/{target.id}', headers=headers).status_code == 204
    assert client.delete(f'/api/v1/me/blocks/{target.id}', headers=headers).status_code == 204
    restored_thread = chat_service.get_chat_thread(db, event.id, viewer.id)
    restored_item = next(item for item in restored_thread.items if item.body == 'Chat body remains readable')
    assert restored_item.body == 'Chat body remains readable'
    assert restored_item.author_label == 'Blocked but visible'
    assert restored_thread.author_labels[target.id] == 'Blocked but visible'

    target.persona_visible = False
    db.commit()
    opted_out_poll = chat_service.get_chat_thread(
        db, event.id, viewer.id, after_sequence=restored_item.sequence,
    )
    assert opted_out_poll.items == []
    assert opted_out_poll.author_labels[target.id] == 'PLM member'


def test_block_cannot_be_created_from_a_comment_hidden_or_removed_for_viewer(
    db, make_user, make_event,
):
    viewer = make_user()
    target = make_user()
    event = make_event()
    comment = _comment(db, event, target)
    db.add(ContentHide(
        id=uid(),
        user_id=viewer.id,
        event_id=event.id,
        kind='comment',
        target_id=comment.id,
    ))
    db.commit()

    with pytest.raises(DomainError) as hidden:
        persona_service.block_user(db, event.id, viewer.id, target.id)
    assert (hidden.value.status, hidden.value.code) == (404, 'persona_unavailable')

    db.delete(db.get(ContentHide, db.scalar(select(ContentHide.id))))
    db.commit()
    stored_comment = db.get(EventComment, comment.id)
    stored_comment.removed_at = now()
    stored_comment.body = None
    db.commit()
    with pytest.raises(DomainError) as removed:
        persona_service.block_user(db, event.id, viewer.id, target.id)
    assert (removed.value.status, removed.value.code) == (404, 'persona_unavailable')


def test_block_accepts_shared_confirmed_participation_but_not_revoked_access(
    db, make_user, make_event,
):
    viewer = make_user()
    target = make_user()
    shared_event = make_event()
    _register(db, shared_event, viewer)
    _register(db, shared_event, target)

    receipt = persona_service.block_user(db, shared_event.id, viewer.id, target.id)
    assert receipt.user_id == target.id

    revoked_event = make_event()
    _register(db, revoked_event, viewer)
    target_registration = _register(db, revoked_event, target)
    db.add(EventAccessRevocation(
        id=uid(),
        event_id=revoked_event.id,
        user_id=target.id,
        cutoff_order=target_registration.admission_order,
    ))
    db.commit()
    with pytest.raises(DomainError) as revoked:
        persona_service.block_user(db, revoked_event.id, viewer.id, target.id)
    assert (revoked.value.status, revoked.value.code) == (404, 'persona_unavailable')


def test_label_metadata_does_not_reveal_removed_hidden_or_revoked_only_authors(db, make_user, make_event):
    viewer = make_user()
    author = make_user(nickname='Private context nickname', persona_visible=True)
    event = make_event()
    _register(db, event, viewer)
    registration = _register(db, event, author)
    comment = _comment(db, event, author)
    message = _message(db, event, author)
    actor = actor_for_user(db, viewer)
    assert social_service.list_comments(db, event.id, actor).author_labels[author.id] == author.nickname
    db.add(ContentHide(id=uid(), user_id=viewer.id, event_id=event.id, kind='comment', target_id=comment.id))
    db.commit()
    assert author.id not in social_service.list_comments(db, event.id, actor).author_labels
    stored_comment = db.get(EventComment, comment.id)
    stored_comment.removed_at = now()
    stored_comment.body = None
    registration.status = 'cancelled'
    db.commit()
    assert author.id not in social_service.list_comments(db, event.id, actor).author_labels
    thread = chat_service.get_chat_thread(db, event.id, viewer.id)
    assert author.id not in thread.author_labels
    assert next(item for item in thread.items if item.id == message.id).body == message.body
    assert next(item for item in thread.items if item.id == message.id).author_label == 'PLM member'


def test_optional_text_controls_roundtrip_clear_and_do_not_grant_privileges(client, make_user, token_for):
    user = make_user()
    headers = {'Authorization': f'Bearer {token_for(user)}'}
    saved = client.patch('/api/v1/me/profile', headers=headers, json={
        'pronouns': 'they/them', 'icebreaker': 'Fictional campus welcome', 'persona_visible': True,
    })
    assert saved.status_code == 200
    assert saved.json()['pronouns'] == 'they/them'
    assert saved.json()['persona_visible'] is True
    required_only = client.patch('/api/v1/me/profile', headers=headers, json={'nickname': 'Updated fictional nickname'})
    assert required_only.json()['pronouns'] == 'they/them'
    assert required_only.json()['icebreaker'] == 'Fictional campus welcome'
    assert required_only.json()['persona_visible'] is True
    cleared = client.patch('/api/v1/me/profile', headers=headers, json={
        'pronouns': None, 'icebreaker': None, 'persona_visible': False,
    })
    assert cleared.status_code == 200
    assert cleared.json()['pronouns'] is None and cleared.json()['icebreaker'] is None
    assert cleared.json()['persona_visible'] is False
    assert client.patch('/api/v1/me/profile', headers=headers, json={'platform_admin': True}).status_code == 422
    assert client.patch('/api/v1/me/profile', headers=headers, json={'persona_visible': 'yes'}).status_code == 422
    assert client.get('/api/v1/me', headers=headers).json()['platform_admin'] is False

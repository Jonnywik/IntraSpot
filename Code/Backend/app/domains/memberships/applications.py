from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.identity.models import User
from app.domains.organizations.models import Organization
from . import policy
from .models import MembershipApplication, MembershipInvitation


WITHDRAWAL_COOLDOWN = timedelta(hours=24)
INVITATION_LIFETIME = timedelta(days=7)


def _organization_name(db: Session, org_id: str) -> str:
    organization = db.get(Organization, org_id)
    if organization is None:
        raise DomainError('organization_not_found', 'Organization was not found.', 404)
    return organization.name


def _application_out(db: Session, application: MembershipApplication, at: datetime) -> dict:
    can_reapply_at = None
    if application.status == 'withdrawn' and application.resolved_at is not None:
        can_reapply_at = application.resolved_at + WITHDRAWAL_COOLDOWN
    return {
        'id': application.id,
        'org_id': application.org_id,
        'organization_name': _organization_name(db, application.org_id),
        'status': application.status,
        'persona_shared': application.persona_shared,
        'created_at': application.created_at,
        'resolved_at': application.resolved_at,
        'decided_by': application.decided_by,
        'reason': application.reason,
        'can_reapply_at': can_reapply_at,
        'access_ready': policy.access_ready(db, application.org_id, application.user_id),
    }


def _application_review(db: Session, application: MembershipApplication, at: datetime) -> dict:
    result = _application_out(db, application, at)
    user = db.get(User, application.user_id)
    persona = None
    label = 'Applicant'
    if application.status == 'pending' and application.persona_shared and user is not None:
        tags = user.tags if isinstance(user.tags, list) else []
        persona = {
            'nickname': user.nickname,
            'tags': [tag for tag in tags if isinstance(tag, str)],
        }
        if user.nickname:
            label = user.nickname
    result.update(user_id=application.user_id, applicant_label=label, persona=persona)
    return result


def _invitation_out(db: Session, invitation: MembershipInvitation, at: datetime) -> dict:
    expired_projection = invitation.status == 'pending' and invitation.expires_at <= at
    return {
        'id': invitation.id,
        'org_id': invitation.org_id,
        'organization_name': _organization_name(db, invitation.org_id),
        'sender_id': invitation.sender_id,
        'recipient_id': invitation.recipient_id,
        'status': 'expired' if expired_projection else invitation.status,
        'created_at': invitation.created_at,
        'expires_at': invitation.expires_at,
        'resolved_at': invitation.expires_at if expired_projection else invitation.resolved_at,
        'access_ready': policy.access_ready(db, invitation.org_id, invitation.recipient_id),
    }


def _active_user(db: Session, user_id: str) -> User:
    user = policy.get_user(db, user_id)
    if user is None:
        raise DomainError('authentication_required', 'Authentication could not be verified.', 401)
    return user


def _lock_pending_applications(db: Session, org_id: str, user_id: str) -> list[MembershipApplication]:
    return list(db.scalars(
        select(MembershipApplication)
        .where(
            MembershipApplication.org_id == org_id,
            MembershipApplication.user_id == user_id,
            MembershipApplication.status == 'pending',
        )
        .order_by(MembershipApplication.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))


def _lock_pending_invitations(
    db: Session,
    org_id: str,
    recipient_id: str | None = None,
) -> list[MembershipInvitation]:
    query = select(MembershipInvitation).where(
        MembershipInvitation.org_id == org_id,
        MembershipInvitation.status == 'pending',
    )
    if recipient_id is not None:
        query = query.where(MembershipInvitation.recipient_id == recipient_id)
    return list(db.scalars(
        query.order_by(MembershipInvitation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))


def _expire_invitations(
    db: Session,
    invitations: list[MembershipInvitation],
    at: datetime,
) -> int:
    expired = 0
    for invitation in invitations:
        if invitation.status == 'pending' and invitation.expires_at <= at:
            invitation.status = 'expired'
            invitation.resolved_at = at
            policy.audit(
                db,
                invitation.org_id,
                None,
                invitation.recipient_id,
                'invitation_expired',
                at,
            )
            expired += 1
    return expired


def _supersede_pending_paths(
    db: Session,
    org_id: str,
    user_id: str,
    actor_id: str,
    at: datetime,
    *,
    keep_application_id: str | None = None,
    keep_invitation_id: str | None = None,
) -> None:
    applications = _lock_pending_applications(db, org_id, user_id)
    invitations = _lock_pending_invitations(db, org_id, user_id)
    _expire_invitations(db, invitations, at)
    for application in applications:
        if application.id == keep_application_id or application.status != 'pending':
            continue
        application.status = 'superseded'
        application.resolved_at = at
        application.decided_by = None
        application.reason = None
        policy.audit(db, org_id, actor_id, user_id, 'application_superseded', at)
    for invitation in invitations:
        if invitation.id == keep_invitation_id or invitation.status != 'pending':
            continue
        invitation.status = 'superseded'
        invitation.resolved_at = at
        policy.audit(db, org_id, actor_id, user_id, 'invitation_superseded', at)


def catch_up_invitations_locked(db: Session, org_id: str, at: datetime) -> int:
    """Persist all expired invitations; caller holds the organization lock."""
    invitations = _lock_pending_invitations(db, org_id)
    changed = _expire_invitations(db, invitations, at)
    if changed:
        db.flush()
    return changed


def create_application(
    db: Session,
    user_id: str,
    org_id: str,
    client_key: str,
    persona_shared: bool,
) -> dict:
    key = str(client_key)
    policy.lock_client_key(db, user_id, key)
    policy.get_org(db, org_id, lock=True, approved=True)
    _active_user(db, user_id)

    existing = db.scalar(
        select(MembershipApplication)
        .where(
            MembershipApplication.user_id == user_id,
            MembershipApplication.client_key == key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        at = now()
        if existing.org_id != org_id or existing.persona_shared is not persona_shared:
            raise DomainError(
                'membership_key_reused',
                'This request key was already used with different membership choices.',
                409,
            )
        return _application_out(db, existing, at)

    pending = _lock_pending_applications(db, org_id, user_id)
    at = now()
    membership = policy.membership_for(db, org_id, user_id)
    if membership is not None and membership.active:
        raise DomainError('membership_already_active', 'You already have an active membership in this organization.', 409)
    if pending:
        raise DomainError('membership_application_pending', 'A membership request is already pending.', 409)

    last_withdrawal = db.scalar(
        select(MembershipApplication.resolved_at)
        .where(
            MembershipApplication.org_id == org_id,
            MembershipApplication.user_id == user_id,
            MembershipApplication.status == 'withdrawn',
        )
        .order_by(MembershipApplication.resolved_at.desc(), MembershipApplication.id.desc())
        .limit(1)
    )
    if last_withdrawal is not None and at < last_withdrawal + WITHDRAWAL_COOLDOWN:
        raise DomainError(
            'membership_withdrawal_cooldown',
            'You can submit another request after the withdrawal cooldown ends.',
            409,
        )

    application = MembershipApplication(
        id=uid(),
        org_id=org_id,
        user_id=user_id,
        client_key=key,
        persona_shared=persona_shared,
        status='pending',
        created_at=at,
    )
    db.add(application)
    policy.audit(db, org_id, user_id, user_id, 'application_submitted', at)
    db.flush()
    return _application_out(db, application, at)


def list_user_applications(db: Session, user_id: str) -> list[dict]:
    rows = db.scalars(
        select(MembershipApplication)
        .where(MembershipApplication.user_id == user_id)
        .order_by(MembershipApplication.created_at.desc(), MembershipApplication.id.desc())
    )
    at = now()
    return [_application_out(db, application, at) for application in rows]


def withdraw_application(db: Session, user_id: str, application_id: str) -> dict:
    preview = db.get(MembershipApplication, application_id)
    if preview is None or preview.user_id != user_id:
        raise DomainError('membership_application_not_found', 'Membership request was not found.', 404)
    policy.get_org(db, preview.org_id, lock=True, approved=True)
    application = db.scalar(
        select(MembershipApplication)
        .where(MembershipApplication.id == application_id, MembershipApplication.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if application is None:
        raise DomainError('membership_application_not_found', 'Membership request was not found.', 404)
    at = now()
    if application.status == 'withdrawn':
        return _application_out(db, application, at)
    if application.status != 'pending':
        raise DomainError('membership_application_closed', 'This membership request is no longer pending.', 409)
    application.status = 'withdrawn'
    application.resolved_at = at
    application.decided_by = None
    application.reason = None
    policy.audit(db, application.org_id, user_id, user_id, 'application_withdrawn', at)
    db.flush()
    return _application_out(db, application, at)


def list_application_reviews(db: Session, reviewer_id: str, org_id: str) -> list[dict]:
    policy.require_staff(db, reviewer_id, org_id)
    rows = db.execute(
        select(MembershipApplication, User)
        .join(User, User.id == MembershipApplication.user_id)
        .where(MembershipApplication.org_id == org_id)
        .order_by(MembershipApplication.created_at.desc(), MembershipApplication.id.desc())
    ).tuples()
    at = now()
    return [_application_review(db, application, at) for application, _user in rows]


def decide_application(
    db: Session,
    reviewer_id: str,
    org_id: str,
    application_id: str,
    outcome: str,
    reason: str | None,
) -> dict:
    policy.require_staff(db, reviewer_id, org_id, lock=True)
    application = db.scalar(
        select(MembershipApplication)
        .where(MembershipApplication.id == application_id, MembershipApplication.org_id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if application is None:
        raise DomainError('membership_application_not_found', 'Membership request was not found.', 404)
    if outcome not in {'approved', 'rejected'}:
        raise DomainError('membership_decision_invalid', 'Choose approval or rejection.', 422)
    if (outcome == 'approved' and reason is not None) or (
        outcome == 'rejected' and reason not in {'requirements_not_met', 'applications_closed', 'other'}
    ):
        raise DomainError('membership_decision_invalid', 'Choose a valid decision reason.', 422)

    if application.status != 'pending':
        if application.status == outcome and application.reason == reason:
            return _application_review(db, application, now())
        raise DomainError('membership_application_decision_conflict', 'This request already has a different outcome.', 409)

    _lock_pending_applications(db, org_id, application.user_id)
    pending_invitations = _lock_pending_invitations(db, org_id, application.user_id)
    at = now()
    _expire_invitations(db, pending_invitations, at)

    application.status = outcome
    application.resolved_at = at
    application.decided_by = reviewer_id
    application.reason = reason
    if outcome == 'approved':
        policy.grant_member_locked(db, org_id, application.user_id, reviewer_id, at)
        _supersede_pending_paths(
            db,
            org_id,
            application.user_id,
            reviewer_id,
            at,
            keep_application_id=application.id,
        )
        policy.notice(
            db,
            org_id,
            application.user_id,
            'membership_approved',
            f'membership_application:{application.id}:approved',
        )
    else:
        policy.notice(
            db,
            org_id,
            application.user_id,
            'membership_rejected',
            f'membership_application:{application.id}:rejected',
        )
    policy.audit(
        db,
        org_id,
        reviewer_id,
        application.user_id,
        f'application_{outcome}',
        at,
    )
    db.flush()
    return _application_review(db, application, at)


def create_invitation(
    db: Session,
    sender_id: str,
    org_id: str,
    recipient_id: str,
    client_key: str,
) -> dict:
    key = str(client_key)
    policy.lock_client_key(db, sender_id, key)
    policy.require_staff(db, sender_id, org_id, roles=('owner', 'admin'), lock=True)

    existing = db.scalar(
        select(MembershipInvitation)
        .where(
            MembershipInvitation.sender_id == sender_id,
            MembershipInvitation.client_key == key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    pending = _lock_pending_invitations(db, org_id, recipient_id)
    at = now()
    _expire_invitations(db, pending, at)
    if existing is not None:
        if existing.org_id != org_id or existing.recipient_id != recipient_id:
            raise DomainError('membership_key_reused', 'This request key was already used for another invitation.', 409)
        return _invitation_out(db, existing, at)

    if policy.get_user(db, recipient_id) is None:
        raise DomainError('membership_invitee_unavailable', 'The invitation recipient is unavailable. Check the shared account code.', 404)

    membership = policy.membership_for(db, org_id, recipient_id)
    if membership is not None and membership.active:
        raise DomainError('membership_already_active', 'This account already has an active membership.', 409)
    if any(invitation.status == 'pending' for invitation in pending):
        raise DomainError('membership_invitation_pending', 'An invitation is already pending for this account.', 409)

    invitation = MembershipInvitation(
        id=uid(),
        org_id=org_id,
        recipient_id=recipient_id,
        sender_id=sender_id,
        client_key=key,
        status='pending',
        created_at=at,
        expires_at=at + INVITATION_LIFETIME,
    )
    db.add(invitation)
    policy.audit(db, org_id, sender_id, recipient_id, 'invitation_sent', at)
    policy.notice(
        db,
        org_id,
        recipient_id,
        'membership_invitation',
        f'membership_invitation:{invitation.id}:sent',
    )
    db.flush()
    return _invitation_out(db, invitation, at)


def list_org_invitations(db: Session, actor_id: str, org_id: str) -> list[dict]:
    policy.require_staff(db, actor_id, org_id, roles=('owner', 'admin'))
    invitations = db.scalars(
        select(MembershipInvitation)
        .where(MembershipInvitation.org_id == org_id)
        .order_by(MembershipInvitation.created_at.desc(), MembershipInvitation.id.desc())
    )
    at = now()
    return [_invitation_out(db, invitation, at) for invitation in invitations]


def list_user_invitations(db: Session, recipient_id: str) -> list[dict]:
    invitations = db.scalars(
        select(MembershipInvitation)
        .where(MembershipInvitation.recipient_id == recipient_id)
        .order_by(MembershipInvitation.created_at.desc(), MembershipInvitation.id.desc())
    )
    at = now()
    return [_invitation_out(db, invitation, at) for invitation in invitations]


def _invitation_for_org(db: Session, org_id: str, invitation_id: str) -> MembershipInvitation:
    invitation = db.scalar(
        select(MembershipInvitation)
        .where(MembershipInvitation.id == invitation_id, MembershipInvitation.org_id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invitation is None:
        raise DomainError('membership_invitation_not_found', 'Membership invitation was not found.', 404)
    return invitation


def revoke_invitation(db: Session, actor_id: str, org_id: str, invitation_id: str) -> dict:
    policy.require_staff(db, actor_id, org_id, roles=('owner', 'admin'), lock=True)
    invitation = _invitation_for_org(db, org_id, invitation_id)
    at = now()
    if invitation.status == 'pending' and invitation.expires_at <= at:
        _expire_invitations(db, [invitation], at)
        db.flush()
        return _invitation_out(db, invitation, at)
    if invitation.status == 'revoked' or invitation.status == 'expired':
        return _invitation_out(db, invitation, at)
    if invitation.status != 'pending':
        raise DomainError('membership_invitation_closed', 'This invitation can no longer be revoked.', 409)
    invitation.status = 'revoked'
    invitation.resolved_at = at
    policy.audit(db, org_id, actor_id, invitation.recipient_id, 'invitation_revoked', at)
    policy.notice(
        db,
        org_id,
        invitation.recipient_id,
        'membership_invitation_revoked',
        f'membership_invitation:{invitation.id}:revoked',
    )
    db.flush()
    return _invitation_out(db, invitation, at)


def _authorized_invitation_preview(db: Session, recipient_id: str, invitation_id: str) -> MembershipInvitation:
    invitation = db.get(MembershipInvitation, invitation_id)
    if invitation is None or invitation.recipient_id != recipient_id:
        raise DomainError('membership_invitation_not_found', 'Membership invitation was not found.', 404)
    return invitation


def accept_invitation(db: Session, recipient_id: str, invitation_id: str) -> dict:
    preview = _authorized_invitation_preview(db, recipient_id, invitation_id)
    policy.get_org(db, preview.org_id, lock=True, approved=True)
    _lock_pending_applications(db, preview.org_id, recipient_id)
    _lock_pending_invitations(db, preview.org_id, recipient_id)
    invitation = _invitation_for_org(db, preview.org_id, invitation_id)
    if invitation.recipient_id != recipient_id:
        raise DomainError('membership_invitation_not_found', 'Membership invitation was not found.', 404)
    at = now()
    if invitation.status == 'accepted':
        return _invitation_out(db, invitation, at)
    if invitation.status == 'pending' and invitation.expires_at <= at:
        raise DomainError(
            'membership_invitation_expired',
            'This invitation has expired.',
            409,
        )
    if invitation.status != 'pending':
        raise DomainError('membership_invitation_closed', 'This invitation can no longer be accepted.', 409)

    policy.grant_member_locked(db, preview.org_id, recipient_id, recipient_id, at)
    invitation.status = 'accepted'
    invitation.resolved_at = at
    _supersede_pending_paths(
        db,
        preview.org_id,
        recipient_id,
        recipient_id,
        at,
        keep_invitation_id=invitation.id,
    )
    policy.audit(db, preview.org_id, recipient_id, recipient_id, 'invitation_accepted', at)
    policy.notice(
        db,
        preview.org_id,
        invitation.sender_id,
        'membership_invitation_accepted',
        f'membership_invitation:{invitation.id}:accepted',
    )
    db.flush()
    return _invitation_out(db, invitation, at)


def decline_invitation(db: Session, recipient_id: str, invitation_id: str) -> dict:
    preview = _authorized_invitation_preview(db, recipient_id, invitation_id)
    policy.get_org(db, preview.org_id, lock=True, approved=True)
    invitation = _invitation_for_org(db, preview.org_id, invitation_id)
    if invitation.recipient_id != recipient_id:
        raise DomainError('membership_invitation_not_found', 'Membership invitation was not found.', 404)
    at = now()
    if invitation.status == 'declined':
        return _invitation_out(db, invitation, at)
    if invitation.status == 'pending' and invitation.expires_at <= at:
        raise DomainError(
            'membership_invitation_expired',
            'This invitation has expired.',
            409,
        )
    if invitation.status != 'pending':
        raise DomainError('membership_invitation_closed', 'This invitation can no longer be declined.', 409)
    invitation.status = 'declined'
    invitation.resolved_at = at
    policy.audit(db, preview.org_id, recipient_id, recipient_id, 'invitation_declined', at)
    policy.notice(
        db,
        preview.org_id,
        invitation.sender_id,
        'membership_invitation_declined',
        f'membership_invitation:{invitation.id}:declined',
    )
    db.flush()
    return _invitation_out(db, invitation, at)

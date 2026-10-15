from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db
from . import applications
from .schemas import (
    MembershipApplicationInput,
    MembershipApplicationOut,
    MembershipApplicationReview,
    MembershipDecisionInput,
    MembershipInvitationInput,
    MembershipInviteOut,
)


router = APIRouter()


@router.post('/organizations/{org_id}/membership-applications', response_model=MembershipApplicationOut)
def create_membership_application(
    org_id: UUID,
    payload: MembershipApplicationInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.create_application(
        db,
        actor.user_id,
        str(org_id),
        str(payload.client_key),
        payload.persona_shared,
    )


@router.get('/me/membership-applications', response_model=list[MembershipApplicationOut])
def my_membership_applications(
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.list_user_applications(db, actor.user_id)


@router.post('/membership-applications/{application_id}/withdraw', response_model=MembershipApplicationOut)
def withdraw_membership_application(
    application_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.withdraw_application(db, actor.user_id, str(application_id))


@router.get(
    '/organizations/{org_id}/membership-applications',
    response_model=list[MembershipApplicationReview],
)
def organization_membership_applications(
    org_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.list_application_reviews(db, actor.user_id, str(org_id))


@router.post(
    '/organizations/{org_id}/membership-applications/{application_id}/decision',
    response_model=MembershipApplicationReview,
)
def decide_membership_application(
    org_id: UUID,
    application_id: UUID,
    payload: MembershipDecisionInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.decide_application(
        db,
        actor.user_id,
        str(org_id),
        str(application_id),
        payload.outcome,
        payload.reason,
    )


@router.post('/organizations/{org_id}/membership-invitations', response_model=MembershipInviteOut)
def create_membership_invitation(
    org_id: UUID,
    payload: MembershipInvitationInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.create_invitation(
        db,
        actor.user_id,
        str(org_id),
        str(payload.recipient_id),
        str(payload.client_key),
    )


@router.get('/organizations/{org_id}/membership-invitations', response_model=list[MembershipInviteOut])
def organization_membership_invitations(
    org_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.list_org_invitations(db, actor.user_id, str(org_id))


@router.post(
    '/organizations/{org_id}/membership-invitations/{invitation_id}/revoke',
    response_model=MembershipInviteOut,
)
def revoke_membership_invitation(
    org_id: UUID,
    invitation_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.revoke_invitation(db, actor.user_id, str(org_id), str(invitation_id))


@router.get('/me/membership-invitations', response_model=list[MembershipInviteOut])
def my_membership_invitations(
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.list_user_invitations(db, actor.user_id)


@router.post('/membership-invitations/{invitation_id}/accept', response_model=MembershipInviteOut)
def accept_membership_invitation(
    invitation_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.accept_invitation(db, actor.user_id, str(invitation_id))


@router.post('/membership-invitations/{invitation_id}/decline', response_model=MembershipInviteOut)
def decline_membership_invitation(
    invitation_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return applications.decline_invitation(db, actor.user_id, str(invitation_id))

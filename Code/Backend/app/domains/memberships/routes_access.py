from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db
from . import access
from .schemas import (
    MembershipAuditOut,
    MembershipChangeOut,
    MembershipKeyInput,
    MembershipRoleInput,
    MembershipRosterItem,
    MembershipSelfOut,
)

router = APIRouter()


@router.get("/me/memberships", response_model=list[MembershipSelfOut])
def my_memberships(
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return access.list_self_memberships(db, actor.user_id)


@router.get("/organizations/{org_id}/members", response_model=list[MembershipRosterItem])
def organization_members(
    org_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return access.list_roster(db, actor.user_id, str(org_id))


@router.get("/organizations/{org_id}/membership-audit", response_model=list[MembershipAuditOut])
def organization_membership_audit(
    org_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return access.list_audit(db, actor.user_id, str(org_id))


@router.patch(
    "/organizations/{org_id}/members/{membership_id}/role",
    response_model=MembershipChangeOut,
)
def change_member_role(
    org_id: UUID,
    membership_id: UUID,
    payload: MembershipRoleInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return access.change_role(db, actor.user_id, str(org_id), str(membership_id), payload)


@router.post(
    "/organizations/{org_id}/members/{membership_id}/remove",
    response_model=MembershipChangeOut,
)
def remove_member(
    org_id: UUID,
    membership_id: UUID,
    payload: MembershipKeyInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return access.remove(
        db, actor.user_id, str(org_id), str(membership_id), payload.client_key,
    )


@router.post("/organizations/{org_id}/membership/leave", response_model=MembershipChangeOut)
def leave_membership(
    org_id: UUID,
    payload: MembershipKeyInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return access.leave(db, actor.user_id, str(org_id), payload.client_key)

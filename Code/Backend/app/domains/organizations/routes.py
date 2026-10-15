from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.session import get_db
from . import service
from .schemas import (
    AccreditationDecisionInput,
    AccreditationDecisionOut,
    MyOrganizationsOut,
    OrganizationApplicationOut,
    OrganizationCreate,
    OrganizationGrantOut,
    OrganizationOut,
    OrganizationWorkspaceOut,
)

router = APIRouter()


@router.get('/organizations', response_model=list[OrganizationOut])
def public_organizations(db: Session = Depends(get_db, scope='function')):
    from .models import Organization
    return list(db.scalars(select(Organization).where(Organization.accreditation_status == 'approved')
                           .order_by(Organization.name, Organization.id)))


def _decision_out(db: Session, org_id: str) -> list[AccreditationDecisionOut]:
    return [AccreditationDecisionOut.model_validate(decision) for decision in service.decisions_for(db, org_id)]


def _workspace_out(db: Session, organization, role: str) -> dict:
    result = OrganizationOut.model_validate(organization).model_dump()
    result.update(role=role, decisions=_decision_out(db, organization.id))
    return result


def _application_out(db: Session, organization) -> dict:
    result = OrganizationOut.model_validate(organization).model_dump()
    result['decisions'] = _decision_out(db, organization.id)
    return result


@router.post('/organizations', response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    return service.create_organization(db, actor, name=payload.name, description=payload.description)


@router.get('/me/organizations', response_model=MyOrganizationsOut)
def my_organizations(actor: Actor = Depends(current_actor), db: Session = Depends(get_db, scope='function')):
    memberships = service.active_memberships(db, actor)
    grants = [OrganizationGrantOut(
        org_id=membership.org_id,
        org_name=organization.name,
        role=membership.role,
        accreditation_status=organization.accreditation_status,
    ) for organization, membership in memberships]
    workspaces = [
        _workspace_out(db, organization, membership.role)
        for organization, membership in memberships
        if membership.role in service.MANAGER_ROLES
    ]
    return {'grants': grants, 'owned_workspaces': workspaces}


@router.get('/platform-admin/organizations', response_model=list[OrganizationApplicationOut])
def admin_organizations(actor: Actor = Depends(current_actor), db: Session = Depends(get_db, scope='function')):
    return [_application_out(db, organization) for organization in service.list_applications(db, actor)]


@router.post(
    '/platform-admin/organizations/{org_id}/accreditation-decision',
    response_model=OrganizationApplicationOut,
)
def accreditation_decision(
    org_id: str,
    payload: AccreditationDecisionInput,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    organization = service.decide_accreditation(db, actor, org_id, payload.outcome)
    return _application_out(db, organization)


@router.get('/organizations/{org_id}', response_model=OrganizationOut)
def public_organization(org_id: str, db: Session = Depends(get_db, scope='function')):
    organization = service.get_organization(db, org_id)
    if organization.accreditation_status != 'approved':
        raise DomainError('organization_not_found', 'Organization was not found.', 404)
    return organization


@router.get('/organizations/{org_id}/workspace', response_model=OrganizationWorkspaceOut)
def organization_workspace(
    org_id: str,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope='function'),
):
    organization, membership = service.require_manager_membership(db, actor, org_id)
    return _workspace_out(db, organization, membership.role)

"""Shared, read-only safety policy. Callers own transactions and lock ordering."""
from sqlalchemy import or_, select

from app.core.errors import DomainError
from app.db.models import now


def discovery_clause(at=None):
    from app.domains.events.models import Event
    from app.domains.eventsafety.models import EventControl, OrganizationSuspension

    restricted = select(EventControl.event_id).where(
        EventControl.event_id == Event.id,
        or_(EventControl.org_hidden, EventControl.platform_hidden,
            EventControl.removed, EventControl.cancelled),
    ).exists()
    suspended = select(OrganizationSuspension.org_id).where(
        OrganizationSuspension.org_id == Event.org_id,
        OrganizationSuspension.suspended_until > (at or now()),
    ).exists()
    return ~restricted & ~suspended


def event_is_terminal(db, event):
    from app.domains.eventsafety.models import EventControl

    return db.scalar(select(EventControl.event_id).where(
        EventControl.event_id == event.id,
        or_(EventControl.removed, EventControl.cancelled),
    )) is not None


def registration_is_available(db, event, at=None):
    from app.domains.events.models import Event
    from app.domains.organizations.models import Organization

    return db.scalar(select(Event.id).join(Organization, Organization.id == Event.org_id).where(
        Event.id == event.id, Event.status == 'published',
        Organization.accreditation_status == 'approved', discovery_clause(at),
    )) is not None


def require_new_registration(db, event, at=None):
    if not registration_is_available(db, event, at):
        raise DomainError('event_registration_unavailable',
                          'This event is not accepting new registrations.', 409)


def require_publishable_event(db, event):
    from app.domains.eventsafety.models import EventControl, OrganizationSuspension

    require_mutable_event(db, event)
    hidden = db.scalar(select(EventControl.event_id).where(
        EventControl.event_id == event.id,
        or_(EventControl.org_hidden, EventControl.platform_hidden),
    ))
    suspended = db.scalar(select(OrganizationSuspension.org_id).where(
        OrganizationSuspension.org_id == event.org_id,
        OrganizationSuspension.suspended_until > now(),
    ))
    if hidden or suspended:
        raise DomainError('event_publication_restricted',
                          'Publishing is unavailable while this event or organization is restricted.', 409)


def require_mutable_event(db, event):
    if event_is_terminal(db, event):
        raise DomainError('event_terminal', 'This event has been cancelled or removed.', 409)


def can_read_event(db, event, viewer_id=None, at=None):
    from app.domains.organizations.models import Organization, OrgMembership
    from app.domains.memberships.policy import eligible_user
    from app.domains.memberships.models import EventAccessRevocation
    from app.domains.registrations.models import Registration

    organization = db.get(Organization, event.org_id)
    if (event.status != 'published' or event_is_terminal(db, event)
            or organization is None or organization.accreditation_status != 'approved'):
        return False
    if registration_is_available(db, event, at):
        return True
    if viewer_id is None or not eligible_user(db, str(viewer_id)):
        return False
    staff = db.scalar(select(OrgMembership.id).where(
        OrgMembership.org_id == event.org_id, OrgMembership.user_id == str(viewer_id),
        OrgMembership.active.is_(True), OrgMembership.role.in_(('owner', 'admin', 'moderator')),
    ))
    if staff:
        return True
    revoked = select(EventAccessRevocation.id).where(
        EventAccessRevocation.event_id == Registration.event_id,
        EventAccessRevocation.user_id == Registration.user_id,
        EventAccessRevocation.cutoff_order >= Registration.admission_order,
    ).exists()
    return db.scalar(select(Registration.id).where(
        Registration.event_id == event.id, Registration.user_id == str(viewer_id),
        Registration.status.in_(('confirmed', 'waitlisted', 'pending', 'reconfirmation_required')),
        ~revoked,
    ).limit(1)) is not None


def require_readable_event(db, event, viewer_id=None, at=None):
    if not can_read_event(db, event, viewer_id, at):
        raise DomainError('event_not_found', 'Event was not found.', 404)

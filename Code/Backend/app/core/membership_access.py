"""Receipt-order revocation, without rewriting historical attendance or retries."""
from sqlalchemy import exists, select


def unrevoked_registration():
    from app.domains.memberships.models import EventAccessRevocation
    from app.domains.registrations.models import Registration

    return ~exists(select(EventAccessRevocation.id).where(
        EventAccessRevocation.event_id == Registration.event_id,
        EventAccessRevocation.user_id == Registration.user_id,
        EventAccessRevocation.cutoff_order >= Registration.admission_order,
    ).correlate(Registration))

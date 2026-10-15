from fastapi import APIRouter
from app.core.errors import ErrorEnvelope


def api_router():
    from app.domains.identity.routes import router as identity
    from app.domains.organizations.routes import router as organizations
    from app.domains.events.routes import router as events
    from app.domains.registrations.routes import router as registrations
    from app.domains.social.routes import router as social
    from app.domains.chat.routes import router as chat
    from app.domains.moderation.routes import router as moderation
    from app.domains.memberships.routes_applications import router as membership_applications
    from app.domains.memberships.routes_access import router as membership_access
    from app.notifications import notification_router
    from app.local_demo import router as local_demo

    router = APIRouter(prefix='/api/v1', responses={status: {'model': ErrorEnvelope}
        for status in (400, 401, 403, 404, 409, 422, 500, 503)})
    for domain in (identity, organizations, events, registrations, social, chat, moderation,
                   membership_applications, membership_access, notification_router(), local_demo):
        router.include_router(domain)
    return router

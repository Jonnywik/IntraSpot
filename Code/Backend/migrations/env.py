from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.session import Base
from app.domains.identity.models import User
from app.domains.organizations.models import Organization, OrgMembership, AccreditationDecision
from app.domains.events.models import Event
from app.domains.registrations.models import RegistrationReceipt, Registration
from app.notifications import Notification
from app.domains.social.models import EventReaction, EventComment
from app.domains.chat.models import ChatMessage
from app.domains.moderation.models import ContentReport, ReportDecision, ContentHide
from app.domains.memberships.models import MembershipApplication, MembershipInvitation, MembershipAudit, MembershipOperation, EventAccessRevocation

target_metadata = Base.metadata


def offline():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()


def online():
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


offline() if context.is_offline_mode() else online()

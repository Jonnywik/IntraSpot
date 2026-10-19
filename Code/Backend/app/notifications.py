from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from uuid import UUID
from pydantic import BaseModel
from sqlalchemy import CheckConstraint, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.models import UTC, now, uid
from app.db.session import Base, get_db


class Notification(Base):
    __tablename__ = 'notifications'
    __table_args__ = (CheckConstraint('event_id IS NOT NULL OR org_id IS NOT NULL', name='ck_notifications_context'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    event_id: Mapped[str | None] = mapped_column(ForeignKey('events.id'), nullable=True)
    org_id: Mapped[str | None] = mapped_column(ForeignKey('organizations.id'), nullable=True)
    registration_id: Mapped[str | None] = mapped_column(ForeignKey('registrations.id'), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), default='waitlist_promoted', nullable=False)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC, default=now, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(UTC, nullable=True)


def notify_in_app(db: Session, *, user_id: str, event_id: str | None = None,
                  org_id: str | None = None,
                  registration_id: str | None = None, kind: str,
                  message: str, dedupe_key: str):
    # The caller holds the event/organization lock and commits with its state change.
    if event_id is None and org_id is None:
        raise ValueError('A notification requires event or organization context.')
    if db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)) is None:
        if org_id is None and event_id is not None:
            from app.domains.events.models import Event
            event = db.get(Event, event_id)
            org_id = event.org_id if event else None
        db.add(Notification(user_id=user_id, event_id=event_id, org_id=org_id,
                            registration_id=registration_id, kind=kind,
                            message=message, dedupe_key=dedupe_key))


def notify_promotion(db: Session, registration):
    notify_in_app(db, user_id=registration.user_id, event_id=registration.event_id,
                  registration_id=registration.id, kind='waitlist_promoted',
                  message='A spot opened. Your attendance is now confirmed.',
                  dedupe_key=f'waitlist_promoted:{registration.id}')


def notify_event_change_members(db: Session, event, revision: int, *, excluded_user_ids=()):
    from app.domains.organizations.models import OrgMembership
    from app.domains.identity.models import User
    from app.domains.identity.service import email_is_eligible

    members = db.scalars(select(User).join(OrgMembership, OrgMembership.user_id == User.id).where(
        OrgMembership.org_id == event.org_id, OrgMembership.active.is_(True), User.active.is_(True)))
    excluded = set(excluded_user_ids)
    for member in members:
        user_id = member.id
        if user_id not in excluded and email_is_eligible(member.email, member.email_verified):
            notify_in_app(db, user_id=user_id, event_id=event.id,
                          kind='event_material_change',
                          message='An event from your organization has changed. Review the updated event details.',
                          dedupe_key=f'event_material_change:{event.id}:revision:{revision}:member:{user_id}')


class NotificationPublic(BaseModel):
    model_config = {'from_attributes': True}
    id: str
    event_id: str | None
    org_id: str | None = None
    kind: str
    message: str
    created_at: datetime
    read_at: datetime | None = None


def notification_router():
    from app.core.auth import current_actor
    router = APIRouter()

    @router.get('/me/notifications', response_model=list[NotificationPublic], tags=['notifications'])
    def notifications(actor: Annotated[Actor, Depends(current_actor)], db: Annotated[Session, Depends(get_db, scope='function')]):
        from app.domains.events.models import Event
        query = (select(Notification, Event.org_id)
                 .outerjoin(Event, Event.id == Notification.event_id)
                 .where(Notification.user_id == actor.user_id))
        if not actor.eligible:
            query = query.where(Notification.kind != 'chat_message')
        return [NotificationPublic.model_validate(notice).model_copy(update={'org_id': notice.org_id or event_org_id})
                for notice, event_org_id in db.execute(query
                    .order_by(Notification.created_at.desc(), Notification.id).limit(100))]

    @router.post('/me/notifications/{notification_id}/read', response_model=NotificationPublic, tags=['notifications'])
    def mark_read(notification_id: UUID, actor: Annotated[Actor, Depends(current_actor)],
                  db: Annotated[Session, Depends(get_db, scope='function')]):
        notice = db.scalar(select(Notification).where(Notification.id == str(notification_id),
                           Notification.user_id == actor.user_id).with_for_update())
        if notice is None or (notice.kind == 'chat_message' and not actor.eligible):
            raise DomainError('notification_not_found', 'Notification was not found.', 404)
        if notice.read_at is None:
            notice.read_at = now()
        db.flush()
        result = NotificationPublic.model_validate(notice)
        if result.org_id is None and notice.event_id is not None:
            from app.domains.events.models import Event
            result.org_id = db.scalar(select(Event.org_id).where(Event.id == notice.event_id))
        return result

    return router

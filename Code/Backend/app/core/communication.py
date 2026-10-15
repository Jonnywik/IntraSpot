"""Shared privacy and pending-person-review policy; not editable profile metadata."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import now
from app.domains.identity.models import User


def require_communication_allowed(db: Session, user_id: str, at=None, *, lock: bool = False) -> None:
    from app.domains.moderation.service import has_pending_person_report

    if lock:
        user = db.scalar(select(User).where(User.id == user_id).with_for_update(key_share=True)
                         .execution_options(populate_existing=True))
        if user is None or not user.active:
            raise DomainError('authentication_required', 'Authentication could not be verified.', 401)
    if has_pending_person_report(db, user_id, at=at or now()):
        raise DomainError('personal_review_pending',
                          'Creating events and sending messages are paused during a personal report review. Existing registrations remain valid.', 403)


def author_label(user: User, viewer_id=None, *, persona_shared=False, before_end=False) -> str:
    if viewer_id == user.id:
        return 'You'
    if (user.persona_visible or (persona_shared and before_end)) and user.nickname:
        return user.nickname
    return 'PLM member'


def is_locally_hidden(db: Session, user_id: str | None, kind: str, target_id: str) -> bool:
    if user_id is None:
        return False
    from app.domains.moderation.models import ContentHide

    return db.scalar(select(ContentHide.id).where(
        ContentHide.user_id == user_id, ContentHide.kind == kind,
        ContentHide.target_id == target_id,
    )) is not None

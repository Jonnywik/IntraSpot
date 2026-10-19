"""Explicit local deadline runner; no migrations or timers at API startup."""
import argparse
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_factory
from app.domains.events.models import Event


def run_once() -> int:
    from app.domains.registrations.service import catch_up_event
    from app.domains.moderation.service import catch_up_reports_locked
    from app.domains.chat.service import purge_event_chat_locked
    from app.domains.memberships.applications import catch_up_invitations_locked
    from app.domains.announcements.report_service import catch_up_announcement_reports_locked
    from app.domains.organizations.models import Organization
    from app.db.models import now

    if get_settings().environment not in {'local', 'test'}:
        raise RuntimeError('This deadline runner is limited to the local MVP.')
    with session_factory()() as db:
        event_ids = list(db.scalars(select(Event.id).where(Event.status == 'published').order_by(Event.id)))
    for event_id in event_ids:
        catch_up_event(event_id)
        with session_factory()() as db, db.begin():
            event = db.scalar(select(Event).where(Event.id == event_id).with_for_update()
                              .execution_options(populate_existing=True))
            if event is not None:
                boundary = now()
                catch_up_reports_locked(db, event, boundary)
                purge_event_chat_locked(db, event, boundary)
    with session_factory()() as db:
        org_ids = list(db.scalars(select(Organization.id).order_by(Organization.id)))
    for org_id in org_ids:
        with session_factory()() as db, db.begin():
            org = db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
            if org is not None:
                boundary = now()
                catch_up_invitations_locked(db, org.id, boundary)
                catch_up_announcement_reports_locked(db, org.id, boundary)
    return len(event_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description='Catch up local registrations, reports, invitations and chat cleanup.')
    parser.add_argument('--once', action='store_true', help='Process once and exit.')
    parser.add_argument('--interval', type=int, default=30, help='Polling interval in seconds (1–3600).')
    args = parser.parse_args()
    if not 1 <= args.interval <= 3600:
        parser.error('interval must be between 1 and 3600 seconds')
    try:
        while True:
            run_once()
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

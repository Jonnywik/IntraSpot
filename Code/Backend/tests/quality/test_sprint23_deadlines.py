"""The explicit runner catches up quiet safety deadlines without incoming requests."""
from datetime import timedelta

from sqlalchemy import func, select

from app import deadlines
from app.db.models import now, uid
from app.domains.eventsafety.models import EventReport, OrganizationSuspension, SafetyAudit
from app.notifications import Notification


def test_runner_purges_due_evidence_and_seals_suspension_once(db, make_org, make_event, monkeypatch):
    boundary = now()
    org = make_org()
    event = make_event(org=org)
    report = EventReport(
        id=uid(), org_id=org.id, event_id=event.id, reporter_id=org.created_by,
        reason='safety', stage='organization', status='open', version=1,
        evidence='{"title":"Fictional retained snapshot"}',
        created_at=boundary - timedelta(days=7), deadline=boundary,
    )
    db.add_all([report, OrganizationSuspension(org_id=org.id, suspended_until=boundary, version=1)])
    db.commit()
    monkeypatch.setattr('app.db.models.now', lambda: boundary)

    for _ in range(2):
        assert deadlines.run_once() >= 1
        db.expire_all()
        persisted = db.get(EventReport, report.id)
        suspension = db.get(OrganizationSuspension, org.id)
        assert (persisted.status, persisted.evidence, persisted.version) == ('expired', None, 2)
        assert (suspension.suspended_until, suspension.version) == (None, 2)
        assert db.scalar(select(func.count(SafetyAudit.id)).where(
            SafetyAudit.org_id == org.id, SafetyAudit.action == 'expire',
        )) == 2
        assert db.scalar(select(func.count(Notification.id)).where(
            Notification.org_id == org.id, Notification.kind == 'organization_safety',
        )) == 1
        db.rollback()

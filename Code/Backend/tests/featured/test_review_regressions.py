from datetime import timedelta

from app.db.models import now
from .conftest import decide_featured, owned_event, request_featured, rows_for_event


def test_mutation_responses_include_the_just_recorded_audit(client, make_event, make_org, make_user, token_for):
    owner, admin = make_user(), make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    requested = request_featured(client, event.id, owner, token_for).json()
    assert [row['action'] for row in requested['decisions']] == ['requested']
    approved = decide_featured(client, requested['id'], admin, token_for, 'approve', requested['version'],
                              ends_at=now() + timedelta(hours=1))
    assert approved.status_code == 200
    assert [row['action'] for row in approved.json()['decisions']] == ['requested', 'approved']
    revoked = decide_featured(client, requested['id'], admin, token_for, 'revoke', approved.json()['version'])
    assert revoked.status_code == 200
    assert [row['action'] for row in revoked.json()['decisions']] == ['requested', 'approved', 'revoked']


def test_approval_rechecks_event_start_after_waiting_for_schedule_lock(client, db, make_event, make_org,
                                                                    make_user, token_for, monkeypatch):
    from app.domains.featured import service
    owner, admin = make_user(), make_user(platform_admin=True)
    event = owned_event(make_event, make_org, owner)
    requested = request_featured(client, event.id, owner, token_for).json()
    before_lock = now()
    times = iter([before_lock, event.starts_at + timedelta(seconds=1)])
    monkeypatch.setattr(service, 'now', lambda: next(times))
    result = decide_featured(client, requested['id'], admin, token_for, 'approve', requested['version'],
                            ends_at=before_lock + timedelta(hours=1))
    assert result.status_code == 409
    row = rows_for_event(db, event.id)[0]
    assert row['status'] == 'pending'
    assert row['version'] == requested['version']

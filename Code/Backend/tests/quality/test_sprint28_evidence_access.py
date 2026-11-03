from datetime import timedelta

import pytest

from app.core.errors import DomainError
from app.db.models import now, uid
from app.domains.eventsafety.models import EventReport
from app.domains.eventsafety.service import _event_evidence
from app.domains.identity.service import actor_for_user
from app.domains.media import service as media_service
from app.domains.media.models import MediaAsset


def _reported_banner(
    db,
    make_user,
    make_org,
    make_event,
    *,
    stage="organization",
    status="open",
    deadline=None,
):
    owner = make_user()
    reporter = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org)
    media_id = uid()
    db.add(
        MediaAsset(
            id=media_id,
            org_id=org.id,
            kind="banner",
            width=1,
            height=1,
            byte_size=1,
            created_by=owner.id,
        )
    )
    db.flush()
    event.banner_media_id = media_id
    db.flush()
    timestamp = now()
    db.add(
        EventReport(
            id=uid(),
            event_id=event.id,
            org_id=org.id,
            reporter_id=reporter.id,
            reason="safety",
            stage=stage,
            status=status,
            version=1,
            evidence=_event_evidence(event),
            created_at=timestamp,
            deadline=deadline or timestamp + timedelta(days=1),
        )
    )
    db.flush()
    event.banner_media_id = None
    db.commit()
    return owner, media_id


def test_detached_report_banner_is_readable_by_org_reviewer(
    db, make_user, make_org, make_event, monkeypatch
):
    owner, media_id = _reported_banner(db, make_user, make_org, make_event)
    monkeypatch.setattr(
        media_service, "read_webp", lambda _media_id, *, db=None: b"retained evidence"
    )

    assert (
        media_service.authorize_and_read(db, actor_for_user(db, owner), media_id)
        == b"retained evidence"
    )


def test_detached_platform_report_banner_is_readable_only_by_platform_reviewer(
    db, make_user, make_org, make_event, monkeypatch
):
    owner, media_id = _reported_banner(
        db, make_user, make_org, make_event, stage="platform", status="escalated"
    )
    platform_admin = make_user(platform_admin=True)
    monkeypatch.setattr(
        media_service, "read_webp", lambda _media_id, *, db=None: b"retained evidence"
    )

    with pytest.raises(DomainError) as denied:
        media_service.authorize_and_read(db, actor_for_user(db, owner), media_id)
    assert denied.value.status == 404
    assert media_service.authorize_and_read(
        db, actor_for_user(db, platform_admin), media_id
    ) == b"retained evidence"


def test_detached_report_banner_denies_guests_and_other_organizations(
    db, make_user, make_org, make_event
):
    _owner, media_id = _reported_banner(db, make_user, make_org, make_event)
    other_org_user = make_user()
    make_org(owner=other_org_user)

    for actor in (None, actor_for_user(db, other_org_user)):
        with pytest.raises(DomainError) as denied:
            media_service.authorize_and_read(db, actor, media_id)
        assert denied.value.status == 404


def test_detached_report_banner_is_denied_after_evidence_deadline(
    db, make_user, make_org, make_event, monkeypatch
):
    owner, media_id = _reported_banner(
        db,
        make_user,
        make_org,
        make_event,
        deadline=now() - timedelta(days=1),
    )
    reads = []
    monkeypatch.setattr(
        media_service,
        "read_webp",
        lambda media_id, *, db=None: reads.append(media_id) or b"must stay unread",
    )

    with pytest.raises(DomainError) as denied:
        media_service.authorize_and_read(db, actor_for_user(db, owner), media_id)

    assert denied.value.status == 404
    assert reads == []


def test_detached_closed_report_banner_is_denied_before_deadline(
    db, make_user, make_org, make_event, monkeypatch
):
    owner, media_id = _reported_banner(
        db,
        make_user,
        make_org,
        make_event,
        status="dismissed",
        deadline=now() + timedelta(days=1),
    )
    reads = []
    monkeypatch.setattr(
        media_service,
        "read_webp",
        lambda media_id, *, db=None: reads.append(media_id) or b"must stay unread",
    )

    with pytest.raises(DomainError) as denied:
        media_service.authorize_and_read(db, actor_for_user(db, owner), media_id)

    assert denied.value.status == 404
    assert reads == []

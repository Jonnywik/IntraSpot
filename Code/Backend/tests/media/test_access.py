"""API authorization and attachment lifecycle coverage for local media."""
from datetime import timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.db.models import now, uid
from app.db.session import Session as DatabaseSession
from app.domains.moderation.models import ContentReport
from app.domains.organizations.models import OrgMembership


@pytest.fixture(autouse=True)
def isolate_media_files(monkeypatch, tmp_path):
    # Keep every API request in this module out of the configured development root.
    monkeypatch.setattr(get_settings(), "media_root", tmp_path)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def versioned(token, version):
    return auth(token) | {"If-Match": f'"{version}"'}


def png_bytes():
    image = Image.new("RGB", (3, 2), (31, 83, 127))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def add_role(db, org, user, role):
    grant = OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role=role, active=True,
    )
    db.add(grant)
    db.commit()
    return grant


def draft_version(client, event, token):
    response = client.get(
        f"/api/v1/events/{event.id}/draft",
        headers=auth(token),
    )
    assert response.status_code == 200
    return response.json()["draft_version"]


def upload_banner(client, event, token, version, body=None, content_type="image/png"):
    headers = versioned(token, version) | {"Content-Type": content_type}
    return client.post(
        f"/api/v1/events/{event.id}/banner",
        headers=headers,
        content=png_bytes() if body is None else body,
    )


def upload_logo(client, org, token, body=None, content_type="image/png"):
    return client.post(
        f"/api/v1/organizations/{org.id}/logo",
        headers=auth(token) | {"Content-Type": content_type},
        content=png_bytes() if body is None else body,
    )


def media_url(response):
    value = response.json()["media_url"]
    assert value.startswith("/api/v1/media/")
    assert "?" not in value
    return value


def test_ineligible_personal_owner_cannot_write_media(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user(email="fictional-ineligible-owner@example.test")
    org = make_org(owner=owner)
    eligible_admin = make_user()
    add_role(db, org, eligible_admin, "admin")
    event = make_event(org=org, status="draft", published_at=None)
    current = draft_version(client, event, token_for(eligible_admin))

    denied = upload_banner(client, event, token_for(owner), current)

    assert denied.status_code == 403
    db.refresh(event)
    assert event.banner_media_id is None


def test_cross_organization_and_moderator_writes_are_denied_but_admin_can_write(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    admin = make_user()
    moderator = make_user()
    add_role(db, org, admin, "admin")
    add_role(db, org, moderator, "moderator")
    event = make_event(org=org, status="draft", published_at=None)
    current = draft_version(client, event, token_for(owner))

    admin_logo = upload_logo(client, org, token_for(admin))
    moderator_banner = upload_banner(client, event, token_for(moderator), current)
    other_owner = make_user()
    make_org(owner=other_owner)
    cross_org_banner = upload_banner(client, event, token_for(other_owner), current)

    assert admin_logo.status_code == 200, admin_logo.json()
    assert moderator_banner.status_code == 403
    assert cross_org_banner.status_code == 403
    db.refresh(event)
    assert event.banner_media_id is None


def test_pending_organization_can_prepare_private_banner_and_logo(
    client, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner, accreditation_status="pending")
    event = make_event(org=org, status="draft", published_at=None)
    owner_token = token_for(owner)
    current = draft_version(client, event, owner_token)

    banner = upload_banner(client, event, owner_token, current)
    logo = upload_logo(client, org, owner_token)

    assert banner.status_code == 200, banner.json()
    assert logo.status_code == 200, logo.json()
    for url in (media_url(banner), media_url(logo)):
        assert client.get(url, headers=auth(owner_token)).status_code == 200
        assert client.get(url).status_code != 200


def test_rejected_organizations_and_published_events_cannot_be_changed(
    client, db, make_user, make_org, make_event, token_for,
):
    rejected_owner = make_user()
    rejected_org = make_org(owner=rejected_owner, accreditation_status="rejected")
    rejected_event = make_event(org=rejected_org, status="draft", published_at=None)
    rejected_version = draft_version(client, rejected_event, token_for(rejected_owner))

    rejected_banner = upload_banner(
        client, rejected_event, token_for(rejected_owner), rejected_version,
    )
    rejected_logo = upload_logo(client, rejected_org, token_for(rejected_owner))

    approved_owner = make_user()
    approved_org = make_org(owner=approved_owner)
    published_event = make_event(org=approved_org)
    published_version = draft_version(client, published_event, token_for(approved_owner))
    published_banner = upload_banner(
        client, published_event, token_for(approved_owner), published_version,
    )

    assert rejected_banner.status_code == 403
    assert rejected_logo.status_code == 403
    assert published_banner.status_code == 409
    db.refresh(rejected_event)
    db.refresh(published_event)
    assert rejected_event.banner_media_id is None
    assert published_event.banner_media_id is None


def test_event_upload_requires_current_if_match_and_stale_retry_preserves_attachment(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, status="draft", published_at=None)
    owner_token = token_for(owner)
    initial = draft_version(client, event, owner_token)

    missing = client.post(
        f"/api/v1/events/{event.id}/banner",
        headers=auth(owner_token) | {"Content-Type": "image/png"},
        content=png_bytes(),
    )
    first = upload_banner(client, event, owner_token, initial)
    stale = upload_banner(client, event, owner_token, initial)

    assert missing.status_code == 428
    assert first.status_code == 200, first.json()
    assert first.json()["draft_version"] != initial
    assert stale.status_code == 409
    assert client.get(media_url(first), headers=auth(owner_token)).status_code == 200
    db.refresh(event)
    assert event.banner_media_id == media_url(first).rsplit("/", 1)[-1]


def test_upload_rejects_mime_spoof_and_streams_over_limit_without_content_length(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, status="draft", published_at=None)
    owner_token = token_for(owner)
    current = draft_version(client, event, owner_token)

    spoofed = upload_banner(
        client, event, owner_token, current, content_type="image/jpeg",
    )
    body = iter((b"x" * (5 * 1024 * 1024), b"x"))
    request = client.build_request(
        "POST",
        f"/api/v1/events/{event.id}/banner",
        headers=versioned(owner_token, current) | {"Content-Type": "image/png"},
        content=body,
    )
    assert "content-length" not in request.headers

    oversized = client.send(request)

    assert spoofed.status_code == 415
    assert oversized.status_code == 413
    db.refresh(event)
    assert event.banner_media_id is None


def test_draft_media_is_private_and_approved_published_media_is_public(
    client, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, status="draft", published_at=None)
    owner_token = token_for(owner)
    banner = upload_banner(
        client, event, owner_token, draft_version(client, event, owner_token),
    )
    assert banner.status_code == 200, banner.json()
    banner_url = media_url(banner)

    assert client.get(banner_url, headers=auth(owner_token)).status_code == 200
    assert client.get(banner_url).status_code != 200

    published = client.post(
        f"/api/v1/events/{event.id}/publish",
        headers=versioned(owner_token, banner.json()["draft_version"]),
    )
    public_event = client.get(f"/api/v1/events/{event.id}")
    public_banner = client.get(banner_url)
    logo = upload_logo(client, org, owner_token)
    public_logo = client.get(media_url(logo))

    assert published.status_code == 200
    assert public_event.status_code == 200
    assert public_event.json()["banner_url"] == banner_url
    assert public_banner.status_code == 200
    assert public_banner.headers["content-type"] == "image/webp"
    assert public_banner.headers["x-content-type-options"] == "nosniff"
    assert public_banner.headers["cache-control"] == "private, no-store"
    assert public_banner.content[:4] == b"RIFF" and public_banner.content[8:12] == b"WEBP"
    assert logo.status_code == 200, logo.json()
    assert public_logo.status_code == 200


def test_replacement_detachment_and_idempotent_removal_restore_theme_fallback(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(
        org=org, status="draft", published_at=None, banner_key=None,
    )
    owner_token = token_for(owner)
    first = upload_banner(
        client, event, owner_token, draft_version(client, event, owner_token),
    )
    assert first.status_code == 200, first.json()
    db.refresh(event)
    assert event.banner_key == "heritage"

    second = upload_banner(
        client, event, owner_token, first.json()["draft_version"],
    )
    assert second.status_code == 200, second.json()
    assert client.get(media_url(first), headers=auth(owner_token)).status_code == 404
    second_url = media_url(second)

    removed = client.delete(
        f"/api/v1/events/{event.id}/banner",
        headers=versioned(owner_token, second.json()["draft_version"]),
    )
    repeated = client.delete(
        f"/api/v1/events/{event.id}/banner",
        headers=versioned(owner_token, removed.json()["draft_version"]),
    )

    assert removed.status_code == 200
    assert removed.json()["media_url"] is None
    assert repeated.status_code == 200
    assert repeated.json()["media_url"] is None
    assert client.get(second_url, headers=auth(owner_token)).status_code == 404
    db.refresh(event)
    assert event.banner_media_id is None
    assert event.banner_key == "heritage"


def test_missing_attached_file_returns_not_found(
    client, make_user, make_org, make_event, token_for, tmp_path,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, status="draft", published_at=None)
    owner_token = token_for(owner)
    uploaded = upload_banner(
        client, event, owner_token, draft_version(client, event, owner_token),
    )
    stored_files = list(tmp_path.rglob("*.webp"))
    assert uploaded.status_code == 200, uploaded.json()
    assert stored_files

    stored_files[0].unlink()
    missing = client.get(media_url(uploaded), headers=auth(owner_token))

    assert missing.status_code == 404


def test_database_rollback_during_replacement_preserves_previous_attachment_and_file(
    client, db, monkeypatch, make_user, make_org, make_event, token_for, tmp_path,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, status="draft", published_at=None)
    owner_token = token_for(owner)
    first = upload_banner(
        client, event, owner_token, draft_version(client, event, owner_token),
    )
    assert first.status_code == 200, first.json()
    old_url = media_url(first)
    old_id = old_url.rsplit("/", 1)[-1]
    old_file = next(tmp_path.rglob("*.webp"))
    original_commit = DatabaseSession.commit
    failed = False

    def fail_one_commit(session):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("simulated database commit failure")
        return original_commit(session)

    monkeypatch.setattr(DatabaseSession, "commit", fail_one_commit)
    failed_upload = client.post(
        f"/api/v1/events/{event.id}/banner",
        headers=versioned(owner_token, first.json()["draft_version"])
        | {"Content-Type": "image/png"},
        content=png_bytes(),
    )

    assert failed_upload.status_code == 500, failed_upload.json()
    db.refresh(event)
    assert event.banner_media_id == old_id
    assert old_file.is_file()
    assert client.get(old_url, headers=auth(owner_token)).status_code == 200


def test_pending_personal_review_blocks_media_writes(
    client, db, make_user, make_org, make_event, token_for,
):
    owner = make_user()
    org = make_org(owner=owner)
    event = make_event(org=org, status="draft", published_at=None)
    reporter = make_user()
    db.add(ContentReport(
        id=uid(), event_id=event.id, org_id=org.id,
        reporter_id=reporter.id, subject_user_id=owner.id,
        kind="person", target_id=owner.id, reason="other",
        status="open", stage="platform", deadline=now() + timedelta(days=2),
    ))
    db.commit()
    current = draft_version(client, event, token_for(owner))

    banner = upload_banner(client, event, token_for(owner), current)
    logo = upload_logo(client, org, token_for(owner))

    assert banner.status_code == 403
    assert logo.status_code == 403
    db.refresh(event)
    assert event.banner_media_id is None

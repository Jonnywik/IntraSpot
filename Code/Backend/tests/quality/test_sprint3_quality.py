import pytest
from sqlalchemy import func, select

from app.core.errors import DomainError
from app.db.models import uid
from app.db.session import session_factory
from app.domains.events.models import Event
from app.domains.registrations import service as registration_service
from app.domains.registrations.models import Registration, RegistrationReceipt
from app.domains.registrations.service import intake_registration


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_draft_intake_is_rejected_and_legacy_receipt_terminalized_on_publish(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    attendee = make_user()
    organization = make_org(owner=owner, accreditation_status="approved")
    event = make_event(org=organization, status="draft", published_at=None)

    # Preserve a pre-fix pending receipt to exercise publication recovery itself.
    legacy_receipt = RegistrationReceipt(
        id=uid(),
        user_id=attendee.id,
        event_id=event.id,
        idempotency_key="legacy-draft-key",
        event_order=1,
    )
    event.next_admission = 1
    db.add(legacy_receipt)
    db.commit()

    # New intake must serialize with publication and reject while the row is draft.
    with pytest.raises(DomainError) as error:
        intake_registration(attendee.id, event.id, "draft-intake-key")
    assert error.value.code == "event_not_found"
    assert db.scalar(
        select(RegistrationReceipt.id).where(
            RegistrationReceipt.user_id == attendee.id,
            RegistrationReceipt.idempotency_key == "draft-intake-key",
        )
    ) is None

    published = client.post(
        f"/api/v1/events/{event.id}/publish", headers=auth(token_for(owner))
    )
    assert published.status_code == 200

    # Publication must terminalize legacy draft receipts before any public read
    # can invoke the normal registration drain.
    db.expire_all()
    terminalized = db.get(RegistrationReceipt, legacy_receipt.id)
    assert terminalized is not None
    assert terminalized.http_status == 404
    assert terminalized.result["error"]["code"] == "event_not_found"
    assert terminalized.processed_at is not None
    original = registration_service.registration_outcome(legacy_receipt.id)
    retry = registration_service.submit_registration(attendee.id, event.id, "legacy-draft-key")
    assert retry == original
    assert retry.http_status == 404

    public_detail = client.get(f"/api/v1/events/{event.id}")
    assert public_detail.status_code == 200
    assert public_detail.json()["confirmed_count"] == 0

    assert db.scalar(
        select(func.count(Registration.id)).where(
            Registration.user_id == attendee.id,
            Registration.event_id == event.id,
        )
    ) == 0


def test_publication_and_legacy_receipt_rejection_roll_back_together(
    client, db, make_user, make_org, make_event, token_for, monkeypatch
):
    owner = make_user()
    attendee = make_user()
    organization = make_org(owner=owner)
    event = make_event(org=organization, status="draft", published_at=None)
    receipt = RegistrationReceipt(
        id=uid(), user_id=attendee.id, event_id=event.id,
        idempotency_key="legacy-rollback-key", event_order=1,
    )
    event.next_admission = 1
    db.add(receipt)
    db.commit()
    original = registration_service.reject_draft_receipts

    def reject_then_fail(session, event_id):
        original(session, event_id)
        raise RuntimeError("simulated publication failure")

    monkeypatch.setattr(registration_service, "reject_draft_receipts", reject_then_fail)
    response = client.post(
        f"/api/v1/events/{event.id}/publish", headers=auth(token_for(owner))
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "simulated publication failure" not in response.text
    with session_factory()() as verification_db:
        stored_event = verification_db.get(Event, event.id)
        stored_receipt = verification_db.get(RegistrationReceipt, receipt.id)
        assert stored_event.status == "draft" and stored_event.published_at is None
        assert stored_receipt.result is None and stored_receipt.http_status is None
        assert stored_receipt.processed_at is None


def test_draft_intake_does_not_allocate_an_admission_order(
    client, db, make_user, make_org, make_event, token_for
):
    owner = make_user()
    attendee = make_user()
    event = make_event(org=make_org(owner=owner), status="draft", published_at=None)
    response = client.post(
        f"/api/v1/events/{event.id}/registrations",
        headers=auth(token_for(attendee)) | {"Idempotency-Key": "private-draft-attempt"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "event_not_found"
    with session_factory()() as verification_db:
        assert verification_db.get(Event, event.id).next_admission == 0
        assert verification_db.scalar(
            select(func.count(RegistrationReceipt.id)).where(RegistrationReceipt.event_id == event.id)
        ) == 0

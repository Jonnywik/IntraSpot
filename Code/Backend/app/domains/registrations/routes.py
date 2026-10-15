from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.domains.registrations import service
from app.domains.registrations.schemas import (
    MyRegistration,
    RegistrationDecisionInput,
    RegistrationInput,
    RegistrationReconfirmationInput,
    RegistrationResult,
    RegistrationReview,
)

router = APIRouter()


def _response(outcome: service.RegistrationOutcome, response: Response) -> dict[str, Any]:
    if outcome.http_status >= 400:
        error = outcome.result.get('error', {})
        raise DomainError(
            str(error.get('code', 'registration_failed')),
            str(error.get('message', 'The registration request could not be completed.')),
            outcome.http_status,
        )
    response.status_code = outcome.http_status
    return outcome.result


@router.post('/events/{event_id}/registrations', response_model=RegistrationResult)
def register(
    event_id: UUID,
    response: Response,
    actor: Annotated[Actor, Depends(current_actor)],
    idempotency_key: Annotated[
        str,
        Header(alias='Idempotency-Key', min_length=8, max_length=128, pattern=r'^[\x20-\x7E]+$'),
    ],
    payload: RegistrationInput | None = None,
):
    outcome = service.submit_registration(
        actor.user_id,
        str(event_id),
        idempotency_key,
        persona_shared=payload.persona_shared if payload is not None else False,
    )
    return _response(outcome, response)


@router.get('/events/{event_id}/registration-review', response_model=list[RegistrationReview])
def registration_review(
    event_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.list_registration_reviews(actor.user_id, str(event_id))


@router.post(
    '/events/{event_id}/registrations/{registration_id}/decision',
    response_model=RegistrationResult,
)
def decide_registration(
    event_id: UUID,
    registration_id: UUID,
    payload: RegistrationDecisionInput,
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.decide_registration(
        actor.user_id,
        str(event_id),
        str(registration_id),
        payload.decision,
    )


@router.post(
    '/events/{event_id}/registrations/me/reconfirmation',
    response_model=RegistrationResult,
)
def reconfirm_registration(
    event_id: UUID,
    payload: RegistrationReconfirmationInput,
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.reconfirm_registration(
        actor.user_id,
        str(event_id),
        payload.accept,
        payload.revision,
    )


@router.get('/me/registrations', response_model=list[MyRegistration])
def my_registrations(actor: Annotated[Actor, Depends(current_actor)]):
    return service.list_my_registrations(actor.user_id)


@router.delete('/events/{event_id}/registrations/me', response_model=RegistrationResult)
def withdraw(
    event_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.withdraw_registration(actor.user_id, str(event_id))

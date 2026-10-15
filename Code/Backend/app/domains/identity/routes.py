from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.session import get_db
from app.domains.identity.models import User
from app.domains.identity.schemas import MeResponse, ProfilePatch, ProfileResponse
from app.domains.identity.service import get_profile_user, update_profile


router = APIRouter()


def _profile_response(user: User) -> ProfileResponse:
    return ProfileResponse(
        nickname=user.nickname,
        age_bracket=user.age_bracket,
        tags=user.tags or [],
        pronouns=user.pronouns,
        icebreaker=user.icebreaker,
        persona_visible=user.persona_visible,
    )


@router.get("/me", response_model=MeResponse)
def read_me(actor: Actor = Depends(current_actor)) -> MeResponse:
    return MeResponse(
        id=actor.user_id,
        nickname=actor.nickname,
        eligible=actor.eligible,
        profile_complete=actor.profile_complete,
        platform_admin=actor.platform_admin,
        grants=list(actor.grants),
        communication_restricted=actor.communication_restricted,
    )


@router.get("/me/profile", response_model=ProfileResponse)
def read_profile(
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> ProfileResponse:
    user = get_profile_user(db, actor.user_id)
    if user is None or not user.active:
        raise DomainError("authentication_required", "Authentication could not be verified.", 401)
    return _profile_response(user)


@router.patch("/me/profile", response_model=ProfileResponse)
def patch_profile(
    changes: ProfilePatch,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> ProfileResponse:
    user = update_profile(db, actor.user_id, changes.model_dump(exclude_unset=True))
    if user is None:
        raise DomainError("authentication_required", "Authentication could not be verified.", 401)
    return _profile_response(user)

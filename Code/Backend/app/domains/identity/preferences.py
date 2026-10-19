from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.models import now
from app.db.session import get_db
from app.domains.identity.preferences_models import UserPreferences


router = APIRouter()


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    language: Literal["en", "fil"] = "en"
    theme: Literal["light", "dark", "system"] = "light"
    text_size: Literal["standard", "large", "extra_large"] = "standard"
    high_contrast: StrictBool = False
    reduced_motion: StrictBool = False
    decoration_paused: StrictBool = False
    show_flash: StrictBool = True


class PreferencesResponse(BaseModel):
    language: Literal["en", "fil"]
    theme: Literal["light", "dark", "system"]
    text_size: Literal["standard", "large", "extra_large"]
    high_contrast: bool
    reduced_motion: bool
    decoration_paused: bool
    show_flash: bool
    initialized: bool
    updated_at: datetime | None


def _response(row: UserPreferences | None) -> PreferencesResponse:
    return PreferencesResponse(
        language=row.language if row else "en",
        theme=row.theme if row else "light",
        text_size=row.text_size if row else "standard",
        high_contrast=row.high_contrast if row else False,
        reduced_motion=row.reduced_motion if row else False,
        decoration_paused=row.decoration_paused if row else False,
        show_flash=row.show_flash if row else True,
        initialized=row is not None,
        updated_at=row.updated_at.astimezone(timezone.utc) if row else None,
    )


def _read_preferences(db: Session, user_id: str) -> PreferencesResponse:
    return _response(db.get(UserPreferences, user_id))


def _set_private_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    vary = [value.strip() for value in response.headers.get("Vary", "").split(",") if value.strip()]
    if not any(value.casefold() == "authorization" for value in vary):
        vary.append("Authorization")
    response.headers["Vary"] = ", ".join(vary)


def _upsert_preferences(
    db: Session, user_id: str, changes: dict[str, str | bool]
) -> PreferencesResponse:
    if not changes:
        return _read_preferences(db, user_id)

    statement = insert(UserPreferences).values(user_id=user_id, updated_at=now(), **changes)
    updated_fields = {field: getattr(statement.excluded, field) for field in changes}
    updated_fields["updated_at"] = statement.excluded.updated_at
    row = db.execute(
        statement.on_conflict_do_update(
            index_elements=[UserPreferences.user_id],
            set_=updated_fields,
        ).returning(UserPreferences)
    ).scalar_one()
    return _response(row)


@router.get("/me/preferences", response_model=PreferencesResponse)
def read_my_preferences(
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> PreferencesResponse:
    _set_private_headers(response)
    return _read_preferences(db, actor.user_id)


@router.patch("/me/preferences", response_model=PreferencesResponse)
def patch_my_preferences(
    changes: PreferencesPatch,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> PreferencesResponse:
    _set_private_headers(response)
    return _upsert_preferences(db, actor.user_id, changes.model_dump(exclude_unset=True))

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.core.discovery import AvailabilityWindow, normalized_label
from app.db.models import now
from app.db.session import get_db
from app.domains.identity.discovery_models import UserDiscoveryPreferences


router = APIRouter()


class DiscoveryPreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    coarse_area: StrictStr | None = Field(default=None, max_length=80)
    availability: list[AvailabilityWindow] = Field(default_factory=list, max_length=28)

    @field_validator("coarse_area", mode="before")
    @classmethod
    def normalize_coarse_area(cls, value):
        if value is None or not isinstance(value, str):
            return value
        if len(value) > 80:
            raise ValueError("Coarse area must be at most 80 characters.")
        normalized = normalized_label(value)
        if len(normalized) > 80:
            raise ValueError("Coarse area must be at most 80 characters after normalization.")
        return normalized or None


class DiscoveryPreferencesResponse(BaseModel):
    coarse_area: StrictStr | None
    availability: list[AvailabilityWindow]
    updated_at: datetime | None


def _response(row: UserDiscoveryPreferences | None) -> DiscoveryPreferencesResponse:
    return DiscoveryPreferencesResponse(
        coarse_area=row.coarse_area if row else None,
        availability=row.availability if row else [],
        updated_at=row.updated_at.astimezone(timezone.utc) if row else None,
    )


def _read_discovery_preferences(db: Session, user_id: str) -> DiscoveryPreferencesResponse:
    return _response(db.get(UserDiscoveryPreferences, user_id))


def _set_private_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    vary = [value.strip() for value in response.headers.get("Vary", "").split(",") if value.strip()]
    if not any(value.casefold() == "authorization" for value in vary):
        vary.append("Authorization")
    response.headers["Vary"] = ", ".join(vary)


def _upsert_discovery_preferences(
    db: Session, user_id: str, changes: dict[str, object]
) -> DiscoveryPreferencesResponse:
    if not changes:
        return _read_discovery_preferences(db, user_id)

    statement = insert(UserDiscoveryPreferences).values(user_id=user_id, updated_at=now(), **changes)
    updated_fields = {field: getattr(statement.excluded, field) for field in changes}
    updated_fields["updated_at"] = statement.excluded.updated_at
    row = db.execute(
        statement.on_conflict_do_update(
            index_elements=[UserDiscoveryPreferences.user_id],
            set_=updated_fields,
        ).returning(UserDiscoveryPreferences)
    ).scalar_one()
    return _response(row)


@router.get("/me/discovery-preferences", response_model=DiscoveryPreferencesResponse)
def read_my_discovery_preferences(
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> DiscoveryPreferencesResponse:
    _set_private_headers(response)
    return _read_discovery_preferences(db, actor.user_id)


@router.patch("/me/discovery-preferences", response_model=DiscoveryPreferencesResponse)
def patch_my_discovery_preferences(
    changes: DiscoveryPreferencesPatch,
    response: Response,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
) -> DiscoveryPreferencesResponse:
    _set_private_headers(response)
    return _upsert_discovery_preferences(
        db,
        actor.user_id,
        changes.model_dump(mode="json", exclude_unset=True),
    )

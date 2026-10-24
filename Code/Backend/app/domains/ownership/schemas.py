from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.domains.memberships.schemas import InputModel


OwnershipTransferStatus = Literal[
    "pending", "accepted", "declined", "revoked", "expired"
]


class OwnershipTransferCreate(InputModel):
    nominee_id: UUID
    client_key: UUID


class OwnershipTransferDecision(InputModel):
    action: Literal["accept", "decline", "revoke"]
    version: Annotated[StrictInt, Field(ge=1)]


class OwnershipTransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    org_id: str
    from_user_id: str
    nominee_id: str
    status: OwnershipTransferStatus
    version: int
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None
    decided_by: str | None

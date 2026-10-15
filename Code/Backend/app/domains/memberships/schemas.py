from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


MembershipReason = Literal['requirements_not_met', 'applications_closed', 'other']
MembershipApplicationStatus = Literal['pending', 'approved', 'rejected', 'withdrawn', 'superseded']
MembershipInvitationStatus = Literal['pending', 'accepted', 'declined', 'revoked', 'expired', 'superseded']


class MembershipApplicationInput(InputModel):
    client_key: UUID
    persona_shared: StrictBool = False


class MembershipDecisionInput(InputModel):
    outcome: Literal['approved', 'rejected']
    reason: MembershipReason | None = None

    @model_validator(mode='after')
    def validate_reason(self):
        if self.outcome == 'rejected' and self.reason is None:
            raise ValueError('A rejection reason is required.')
        if self.outcome == 'approved' and self.reason is not None:
            raise ValueError('Approval cannot include a rejection reason.')
        return self


class MembershipInvitationInput(InputModel):
    recipient_id: UUID
    client_key: UUID


class MembershipKeyInput(InputModel):
    client_key: UUID


class MembershipRoleInput(MembershipKeyInput):
    role: Literal['admin', 'moderator', 'member']


class MembershipApplicationOut(BaseModel):
    id: str
    org_id: str
    organization_name: str
    status: MembershipApplicationStatus
    persona_shared: bool
    created_at: datetime
    resolved_at: datetime | None
    decided_by: str | None
    reason: MembershipReason | None
    can_reapply_at: datetime | None
    access_ready: bool


class MembershipPersona(BaseModel):
    nickname: str | None
    tags: list[str]


class MembershipApplicationReview(MembershipApplicationOut):
    user_id: str
    applicant_label: str
    persona: MembershipPersona | None


class MembershipInviteOut(BaseModel):
    id: str
    org_id: str
    organization_name: str
    sender_id: str
    recipient_id: str
    status: MembershipInvitationStatus
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None
    access_ready: bool


class MembershipSelfOut(BaseModel):
    id: str
    org_id: str
    organization_name: str
    role: Literal['owner', 'admin', 'moderator', 'member']
    active: bool
    access_ready: bool
    joined_at: datetime | None


class MembershipRosterItem(BaseModel):
    id: str
    user_id: str
    label: str
    role: Literal['owner', 'admin', 'moderator', 'member']
    eligible: bool
    access_ready: bool
    joined_at: datetime | None


class MembershipChangeOut(BaseModel):
    org_id: str
    membership_id: str
    user_id: str
    role: Literal['owner', 'admin', 'moderator', 'member']
    active: bool
    cancelled_registrations: int
    chat_revoked: int


class MembershipAuditOut(BaseModel):
    id: str
    actor_id: str | None
    user_id: str
    action: str
    old_role: str | None
    new_role: str | None
    created_at: datetime

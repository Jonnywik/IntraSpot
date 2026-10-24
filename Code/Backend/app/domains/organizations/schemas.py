from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OrganizationCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ''

    @field_validator('name')
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Name is required.')
        return value


class AccreditationDecisionInput(InputModel):
    outcome: Literal['approved', 'rejected']


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    logo_url: str | None = None
    accreditation_status: Literal['pending', 'approved', 'rejected']
    created_at: datetime


class AccreditationDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    outcome: Literal['approved', 'rejected']
    admin_id: str
    decided_at: datetime


class OrganizationWorkspaceOut(OrganizationOut):
    role: Literal['owner', 'admin']
    decisions: list[AccreditationDecisionOut]


class OrganizationApplicationOut(OrganizationOut):
    decisions: list[AccreditationDecisionOut]


class OrganizationGrantOut(BaseModel):
    org_id: str
    org_name: str
    role: Literal['owner', 'admin', 'moderator', 'member']
    accreditation_status: Literal['pending', 'approved', 'rejected']


class MyOrganizationsOut(BaseModel):
    grants: list[OrganizationGrantOut]
    owned_workspaces: list[OrganizationWorkspaceOut]

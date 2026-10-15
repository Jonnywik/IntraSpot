from dataclasses import dataclass


@dataclass(frozen=True)
class OrgGrant:
    org_id: str
    org_name: str
    role: str
    accreditation_status: str


@dataclass(frozen=True)
class Actor:
    user_id: str
    nickname: str | None
    eligible: bool
    profile_complete: bool
    platform_admin: bool
    grants: tuple[OrgGrant, ...] = ()
    communication_restricted: bool = False

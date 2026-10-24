from pydantic import ValidationError
import pytest
from uuid import uuid4

from app.domains.ownership.models import OwnershipTransfer, OwnershipTransferAudit
from app.domains.ownership.schemas import OwnershipTransferCreate, OwnershipTransferDecision


def test_ownership_model_contract_matches_migration_names():
    transfer = OwnershipTransfer.__table__
    assert transfer.name == "ownership_transfers"
    assert set(transfer.columns.keys()) == {
        "id", "org_id", "from_user_id", "nominee_id", "client_key", "status",
        "version", "created_at", "expires_at", "resolved_at", "decided_by",
    }
    assert all(transfer.c[name].type.length == 36 for name in (
        "id", "org_id", "from_user_id", "nominee_id", "client_key", "decided_by",
    ))
    assert transfer.c.status.type.length == 16
    assert transfer.c.version.type.python_type is int
    assert transfer.c.created_at.type.timezone is True
    assert transfer.c.expires_at.type.timezone is True
    assert transfer.c.resolved_at.type.timezone is True
    assert transfer.c.created_at.nullable is False
    assert transfer.c.expires_at.nullable is False
    assert transfer.c.resolved_at.nullable is True
    assert transfer.c.decided_by.nullable is True
    assert {constraint.name for constraint in transfer.constraints if constraint.name} >= {
        "uq_ownership_transfers_from_key",
        "ck_ownership_transfers_status",
        "ck_ownership_transfers_distinct_users",
        "ck_ownership_transfers_version",
        "ck_ownership_transfers_expiry",
    }
    assert {index.name for index in transfer.indexes} >= {
        "uq_ownership_transfers_pending_org",
        "ix_ownership_transfers_org_created",
    }
    assert {fk.target_fullname for fk in transfer.c.org_id.foreign_keys} == {
        "organizations.id",
    }
    assert {fk.target_fullname for fk in transfer.c.from_user_id.foreign_keys} == {
        "users.id",
    }
    assert {fk.target_fullname for fk in transfer.c.nominee_id.foreign_keys} == {
        "users.id",
    }
    assert {fk.target_fullname for fk in transfer.c.decided_by.foreign_keys} == {
        "users.id",
    }

    audit = OwnershipTransferAudit.__table__
    assert audit.name == "ownership_transfer_audits"
    assert set(audit.columns.keys()) == {
        "id", "transfer_id", "actor_id", "action", "created_at",
    }
    assert all(audit.c[name].type.length == 36 for name in (
        "id", "transfer_id", "actor_id",
    ))
    assert audit.c.action.type.length == 16
    assert audit.c.created_at.type.timezone is True
    assert audit.c.actor_id.nullable is True
    assert {fk.target_fullname for fk in audit.c.transfer_id.foreign_keys} == {
        "ownership_transfers.id",
    }
    assert {fk.target_fullname for fk in audit.c.actor_id.foreign_keys} == {
        "users.id",
    }
    assert {constraint.name for constraint in audit.constraints if constraint.name} >= {
        "ck_ownership_transfer_audits_action",
    }
    assert {index.name for index in audit.indexes} >= {
        "ix_ownership_transfer_audits_transfer_created",
    }


def test_transfer_request_inputs_are_strict_and_forbid_extra_fields():
    nominee_id = uuid4()
    client_key = uuid4()
    assert OwnershipTransferCreate(nominee_id=nominee_id, client_key=client_key)
    assert OwnershipTransferCreate.model_config["extra"] == "forbid"
    assert OwnershipTransferDecision.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        OwnershipTransferCreate(
            nominee_id=nominee_id,
            client_key=client_key,
            expires_at="2030-01-01T00:00:00Z",
        )

    for version in (True, "1", 0, -1):
        with pytest.raises(ValidationError):
            OwnershipTransferDecision(action="accept", version=version)
    assert OwnershipTransferDecision(action="accept", version=1).version == 1

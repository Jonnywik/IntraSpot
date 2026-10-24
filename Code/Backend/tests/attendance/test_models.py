from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.attendance.models import AttendanceAudit, AttendanceSession
from app.domains.attendance.schemas import AttendanceMarkInput, AttendanceSessionInput


def test_attendance_orm_constraint_names_and_created_at_default_match_migration():
    session_checks = {
        constraint.name for constraint in AttendanceSession.__table__.constraints
        if constraint.name and constraint.__class__.__name__ == "CheckConstraint"
    }
    audit_checks = {
        constraint.name for constraint in AttendanceAudit.__table__.constraints
        if constraint.name and constraint.__class__.__name__ == "CheckConstraint"
    }
    audit_uniques = {
        constraint.name for constraint in AttendanceAudit.__table__.constraints
        if constraint.name and constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert "ck_attendance_sessions_version" in session_checks
    assert "ck_attendance_audits_version" in audit_checks
    assert "uq_attendance_audits_actor_key" in audit_uniques
    created_at = AttendanceAudit.__table__.c.created_at
    assert created_at.default is not None
    assert created_at.server_default is None


@pytest.mark.parametrize(
    ("schema", "field", "bad_value"),
    (
        (AttendanceSessionInput, "is_open", 1),
        (AttendanceSessionInput, "version", True),
        (AttendanceMarkInput, "attended", "true"),
        (AttendanceMarkInput, "version", "0"),
    ),
)
def test_mutation_inputs_reject_coercion_and_extra_fields(schema, field, bad_value):
    values = {"version": 0, "client_key": uuid4()}
    values["is_open" if schema is AttendanceSessionInput else "attended"] = False
    invalid = values.copy()
    invalid[field] = bad_value
    with pytest.raises(ValidationError):
        schema(**invalid)

    values["unexpected"] = "forbidden"
    with pytest.raises(ValidationError):
        schema(**values)

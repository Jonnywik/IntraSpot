from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import current_actor
from app.core.contracts import Actor
from app.db.session import get_db

from . import service
from .schemas import (
    AttendanceAuditOut,
    AttendanceMarkInput,
    AttendanceMutationOut,
    AttendanceOut,
    AttendanceSessionInput,
)


router = APIRouter()


@router.get("/events/{event_id}/attendance", response_model=AttendanceOut)
def get_attendance(
    event_id: UUID,
    db: Annotated[Session, Depends(get_db, scope="function")],
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.get_attendance(db, actor.user_id, str(event_id))


@router.get(
    "/events/{event_id}/attendance/history",
    response_model=list[AttendanceAuditOut],
)
def list_attendance_history(
    event_id: UUID,
    db: Annotated[Session, Depends(get_db, scope="function")],
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.list_attendance_history(db, actor.user_id, str(event_id))


@router.post(
    "/events/{event_id}/attendance/session",
    response_model=AttendanceMutationOut,
)
def set_attendance_session(
    event_id: UUID,
    payload: AttendanceSessionInput,
    db: Annotated[Session, Depends(get_db, scope="function")],
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.set_attendance_session(db, actor.user_id, str(event_id), payload)


@router.put(
    "/events/{event_id}/attendance/registrations/{registration_id}",
    response_model=AttendanceMutationOut,
)
def set_registration_attendance(
    event_id: UUID,
    registration_id: UUID,
    payload: AttendanceMarkInput,
    db: Annotated[Session, Depends(get_db, scope="function")],
    actor: Annotated[Actor, Depends(current_actor)],
):
    return service.set_registration_attendance(
        db, actor.user_id, str(event_id), str(registration_id), payload,
    )

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.auth import current_actor, optional_actor
from app.core.contracts import Actor
from app.core.errors import DomainError, ErrorEnvelope
from app.db.session import get_db
from app.domains.media.codec import (
    MAX_INPUT_BYTES,
    InvalidMediaInput,
    NormalizedImage,
    UnsupportedMediaType,
    normalize_image,
    validate_content_type,
)
from app.domains.media.schemas import MediaMutationOut
from app.domains.media.service import (
    authorize_and_read,
    authorize_banner_upload,
    authorize_logo_upload,
    remove_banner,
    remove_logo,
    upload_banner,
    upload_logo,
)


router = APIRouter()

_RAW_IMAGE_REQUEST_BODY = {
    "required": True,
    "content": {
        media_type: {"schema": {"type": "string", "format": "binary"}}
        for media_type in ("image/jpeg", "image/png", "image/webp")
    },
}
_UPLOAD_RESPONSES = {
    413: {"model": ErrorEnvelope, "description": "Image upload exceeds 5 MiB."},
    415: {"model": ErrorEnvelope, "description": "Unsupported or mismatched image Content-Type."},
}
_BANNER_RESPONSES = {
    **_UPLOAD_RESPONSES,
    428: {"model": ErrorEnvelope, "description": "If-Match is required."},
}


async def _read_bounded_body(request: Request) -> bytes:
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            size = int(declared_length)
        except ValueError:
            raise DomainError("invalid_media_request", "Image upload is invalid.", 400) from None
        if size < 0:
            raise DomainError("invalid_media_request", "Image upload is invalid.", 400)
        if size > MAX_INPUT_BYTES:
            raise DomainError("media_too_large", "Image uploads must be 5 MiB or smaller.", 413)

    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > MAX_INPUT_BYTES:
            raise DomainError("media_too_large", "Image uploads must be 5 MiB or smaller.", 413)
        chunks.append(chunk)
    return b"".join(chunks)


def _image(content: bytes, content_type: str) -> NormalizedImage:
    try:
        return normalize_image(content, content_type)
    except UnsupportedMediaType:
        raise DomainError(
            "unsupported_media_type",
            "Use a JPEG, PNG, or WebP image with its matching Content-Type.",
            415,
        ) from None
    except InvalidMediaInput:
        raise DomainError("invalid_image", "Image upload is invalid.", 422) from None


def _check_content_type(content_type: str | None) -> str:
    try:
        return validate_content_type(content_type)
    except UnsupportedMediaType:
        raise DomainError(
            "unsupported_media_type",
            "Use a JPEG, PNG, or WebP image with its matching Content-Type.",
            415,
        ) from None


@router.post(
    "/events/{event_id}/banner",
    response_model=MediaMutationOut,
    openapi_extra={"requestBody": _RAW_IMAGE_REQUEST_BODY},
    responses=_BANNER_RESPONSES,
)
async def upload_event_banner(
    event_id: UUID,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    await run_in_threadpool(authorize_banner_upload, db, actor, str(event_id))
    if if_match is None:
        raise DomainError("precondition_required", "If-Match is required for event media changes.", 428)
    content_type = _check_content_type(request.headers.get("content-type"))
    content = await _read_bounded_body(request)
    image = await run_in_threadpool(_image, content, content_type)
    return await run_in_threadpool(upload_banner, db, actor, str(event_id), if_match, image)


@router.delete(
    "/events/{event_id}/banner",
    response_model=MediaMutationOut,
    responses={428: {"model": ErrorEnvelope, "description": "If-Match is required."}},
)
def delete_event_banner(
    event_id: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return remove_banner(db, actor, str(event_id), if_match)


@router.post(
    "/organizations/{org_id}/logo",
    response_model=MediaMutationOut,
    openapi_extra={"requestBody": _RAW_IMAGE_REQUEST_BODY},
    responses=_UPLOAD_RESPONSES,
)
async def upload_organization_logo(
    org_id: UUID,
    request: Request,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    await run_in_threadpool(authorize_logo_upload, db, actor, str(org_id))
    content_type = _check_content_type(request.headers.get("content-type"))
    content = await _read_bounded_body(request)
    image = await run_in_threadpool(_image, content, content_type)
    return await run_in_threadpool(upload_logo, db, actor, str(org_id), image)


@router.delete("/organizations/{org_id}/logo", response_model=MediaMutationOut)
def delete_organization_logo(
    org_id: UUID,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db, scope="function"),
):
    return remove_logo(db, actor, str(org_id))


@router.get("/media/{media_id}")
def get_media(
    media_id: str,
    actor: Actor | None = Depends(optional_actor),
    db: Session = Depends(get_db, scope="function"),
):
    content = authorize_and_read(db, actor, media_id)
    return Response(
        content=content,
        media_type="image/webp",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )

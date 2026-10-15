from uuid import UUID

import jwt
from fastapi import Depends, Request
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.session import get_db
from app.domains.identity.service import actor_for_user, get_active_user


def _authentication_error() -> DomainError:
    return DomainError("authentication_required", "Authentication could not be verified.", 401)


def _bearer_token(authorization: str | None, *, required: bool) -> str | None:
    if authorization is None:
        if required:
            raise _authentication_error()
        return None

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].casefold() != "bearer" or not parts[1] or any(c.isspace() for c in parts[1]):
        raise _authentication_error()
    return parts[1]


def _actor_from_authorization(authorization: str | None, db: Session, *, required: bool) -> Actor | None:
    token = _bearer_token(authorization, required=required)
    if token is None:
        return None

    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_public_key_file.read_text(encoding="utf-8"),
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        if not isinstance(claims, dict):
            raise ValueError("invalid claims")
        subject = claims.get("sub")
        if not isinstance(subject, str):
            raise ValueError("invalid subject")
        user_id = str(UUID(subject))
    except (PyJWTError, OSError, TypeError, ValueError, OverflowError):
        raise _authentication_error() from None

    user = get_active_user(db, user_id)
    if user is None:
        raise _authentication_error()
    return actor_for_user(db, user)


def current_actor(request: Request, db: Session = Depends(get_db, scope="function")) -> Actor:
    actor = _actor_from_authorization(request.headers.get("authorization"), db, required=True)
    if actor is None:
        raise _authentication_error()
    return actor


def optional_actor(request: Request, db: Session = Depends(get_db, scope="function")) -> Actor | None:
    return _actor_from_authorization(request.headers.get("authorization"), db, required=False)


def require_eligible(actor: Actor = Depends(current_actor)) -> Actor:
    if not actor.eligible:
        raise DomainError("plm_email_required", "A verified PLM email address is required.", 403)
    return actor

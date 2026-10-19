from dataclasses import dataclass
from functools import lru_cache
from http.client import HTTPException
from json import JSONDecodeError, loads
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

import jwt
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.contracts import Actor
from app.core.errors import DomainError
from app.db.session import session_factory
from app.domains.identity.models import User
from app.domains.identity.service import actor_for_user, get_active_user


_ALLOWED_ALGORITHMS = frozenset({"ES256", "RS256"})
_MAX_TOKEN_LENGTH = 16_384
_MAX_KID_LENGTH = 128
_JWKS_TIMEOUT_SECONDS = 3
_JWKS_BODY_LIMIT = 256 * 1024
_AUTH_TIMEOUT_SECONDS = 3
_AUTH_BODY_LIMIT = 64 * 1024
_PROVISION_ATTEMPTS = 3


@dataclass(frozen=True)
class VerifiedSupabaseIdentity:
    user_id: str
    email: str
    email_verified: bool


def _authentication_error() -> DomainError:
    return DomainError("authentication_required", "Authentication could not be verified.", 401)


def _provider_unavailable() -> DomainError:
    return DomainError("identity_provider_unavailable", "Authentication is temporarily unavailable.", 503)


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    return _BoundedPyJWKClient(
        f"{issuer}/.well-known/jwks.json",
        cache_keys=False,
        cache_jwk_set=True,
        lifespan=300,
        timeout=_JWKS_TIMEOUT_SECONDS,
    )


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _BoundedPyJWKClient(jwt.PyJWKClient):
    def fetch_data(self) -> Any:
        try:
            request = Request(url=self.uri, headers=self.headers)
            with build_opener(_NoRedirectHandler()).open(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                if status != 200:
                    raise PyJWKClientConnectionError("The trusted JWKS endpoint returned an error.")

                body = response.read(_JWKS_BODY_LIMIT + 1)
            if not isinstance(body, bytes) or len(body) > _JWKS_BODY_LIMIT:
                raise PyJWKClientConnectionError("The trusted JWKS response exceeded its size limit.")

            parsed_jwk_set = loads(body)
            if (
                not isinstance(parsed_jwk_set, dict)
                or not isinstance(parsed_jwk_set.get("keys"), list)
                or not parsed_jwk_set["keys"]
            ):
                raise PyJWKClientConnectionError("The trusted JWKS response was malformed.")
            jwt.PyJWKSet.from_dict(parsed_jwk_set)
            if self.jwk_set_cache is not None:
                self.jwk_set_cache.put(parsed_jwk_set)
            self._last_successful_fetch = monotonic()
            return parsed_jwk_set
        except PyJWKClientConnectionError:
            raise
        except HTTPError as error:
            error.close()
            raise PyJWKClientConnectionError("Could not fetch the trusted JWKS.") from None
        except (HTTPException, URLError, TimeoutError, OSError, PyJWTError, ValueError, RecursionError):
            raise PyJWKClientConnectionError("Could not fetch the trusted JWKS.") from None


def _trusted_auth_user(token: str, settings: Settings) -> dict[str, Any]:
    try:
        issuer = settings.supabase_issuer
        publishable_key = settings.supabase_publishable_key
    except (AttributeError, ValueError):
        raise _provider_unavailable() from None
    if not publishable_key:
        raise _provider_unavailable()

    request = Request(
        f"{issuer}/user",
        headers={
            "Accept": "application/json",
            "apikey": publishable_key,
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    try:
        with build_opener(_NoRedirectHandler()).open(request, timeout=_AUTH_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                if status in {400, 401, 403}:
                    raise _authentication_error()
                raise _provider_unavailable()
            body = response.read(_AUTH_BODY_LIMIT + 1)
    except DomainError:
        raise
    except HTTPError as error:
        status = error.code
        error.close()
        if status in {400, 401, 403}:
            raise _authentication_error() from None
        raise _provider_unavailable() from None
    except (HTTPException, URLError, TimeoutError, OSError):
        raise _provider_unavailable() from None

    if len(body) > _AUTH_BODY_LIMIT:
        raise _provider_unavailable()
    try:
        payload = loads(body.decode("utf-8"))
    except (JSONDecodeError, UnicodeDecodeError, TypeError, ValueError, RecursionError):
        raise _provider_unavailable() from None
    if not isinstance(payload, dict):
        raise _provider_unavailable()
    return payload


def _uuid_claim(claims: dict[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or len(value) != 36:
        raise _authentication_error()
    try:
        parsed = UUID(value)
    except ValueError:
        raise _authentication_error() from None
    if str(parsed) != value.casefold():
        raise _authentication_error()
    return str(parsed)


def _identity_from_auth_user(user: dict[str, Any], user_id: str) -> VerifiedSupabaseIdentity:
    trusted_id = user.get("id")
    if not isinstance(trusted_id, str) or trusted_id != user_id:
        raise _authentication_error()
    if user.get("is_anonymous") is not False:
        raise _authentication_error()

    identities = user.get("identities")
    if not isinstance(identities, list) or not any(
        isinstance(identity, dict) and identity.get("provider") == "google"
        for identity in identities
    ):
        raise _authentication_error()

    email = user.get("email")
    if (
        not isinstance(email, str)
        or not email
        or len(email) > 254
        or email.strip() != email
        or any(character.isspace() or ord(character) < 32 for character in email)
        or email.count("@") != 1
    ):
        raise _authentication_error()
    local_part, domain = email.split("@", 1)
    if not local_part or not domain:
        raise _authentication_error()

    if "email_confirmed_at" not in user:
        raise _provider_unavailable()
    confirmed_at = user["email_confirmed_at"]
    if confirmed_at is None:
        email_verified = False
    elif isinstance(confirmed_at, str) and confirmed_at.strip():
        email_verified = True
    else:
        raise _provider_unavailable()

    return VerifiedSupabaseIdentity(user_id=user_id, email=email, email_verified=email_verified)


def verify_supabase_identity(token: str, settings: Settings) -> VerifiedSupabaseIdentity:
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH:
        raise _authentication_error()
    segments = token.split(".")
    if (
        len(segments) != 3
        or any(not segment for segment in segments)
        or any(
            not character.isascii() or not (character.isalnum() or character in "._-")
            for character in token
        )
    ):
        raise _authentication_error()
    try:
        issuer = settings.supabase_issuer
    except (AttributeError, ValueError):
        raise _provider_unavailable() from None

    try:
        header = jwt.get_unverified_header(token)
        # Reject malformed/deep payloads before network access. No identity or
        # permission is derived here; the signature and all claims verify below.
        jwt.decode(token, options={"verify_signature": False})
    except (PyJWTError, TypeError, ValueError, OverflowError, RecursionError):
        raise _authentication_error() from None
    if not isinstance(header, dict):
        raise _authentication_error()
    algorithm = header.get("alg")
    kid = header.get("kid")
    if (
        not isinstance(algorithm, str)
        or algorithm not in _ALLOWED_ALGORITHMS
        or not isinstance(kid, str)
        or not 1 <= len(kid) <= _MAX_KID_LENGTH
        or not kid.isascii()
        or not kid.isprintable()
        or any(character.isspace() for character in kid)
        or header.get("typ") not in (None, "JWT")
        or any(name not in {"alg", "kid", "typ"} for name in header)
    ):
        raise _authentication_error()

    try:
        signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError:
        raise _provider_unavailable() from None
    except PyJWKClientError:
        raise _authentication_error() from None
    except PyJWTError:
        raise _provider_unavailable() from None
    except (URLError, TimeoutError, OSError):
        raise _provider_unavailable() from None
    except (PyJWTError, TypeError, ValueError, OverflowError, RecursionError):
        raise _authentication_error() from None

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "session_id", "role"]},
        )
    except (PyJWTError, TypeError, ValueError, OverflowError, RecursionError):
        raise _authentication_error() from None
    if (
        not isinstance(claims, dict)
        or claims.get("aud") != "authenticated"
        or claims.get("role") != "authenticated"
        or claims.get("is_anonymous") is True
    ):
        raise _authentication_error()

    user_id = _uuid_claim(claims, "sub")
    _uuid_claim(claims, "session_id")
    trusted_user = _trusted_auth_user(token, settings)
    return _identity_from_auth_user(trusted_user, user_id)


def _synchronize_trusted_email(db: Session, user: User, identity: VerifiedSupabaseIdentity) -> User:
    if user.email == identity.email and user.email_verified is identity.email_verified:
        return user
    try:
        with db.begin_nested():
            user.email = identity.email
            user.email_verified = identity.email_verified
            db.flush()
    except IntegrityError:
        raise _authentication_error() from None
    return user


def provision_supabase_user(db: Session, identity: VerifiedSupabaseIdentity) -> User:
    for attempt in range(_PROVISION_ATTEMPTS):
        user = db.scalar(select(User).where(User.id == identity.user_id))
        if user is not None:
            return _synchronize_trusted_email(db, user, identity)

        email_owner = db.scalar(select(User).where(User.email == identity.email))
        if email_owner is not None:
            raise _authentication_error()

        user = User(
            id=identity.user_id,
            email=identity.email,
            email_verified=identity.email_verified,
            active=True,
            platform_admin=False,
            nickname=None,
            age_bracket=None,
            tags=[],
            pronouns=None,
            icebreaker=None,
            persona_visible=False,
        )
        try:
            with db.begin_nested():
                db.add(user)
                db.flush()
            return user
        except IntegrityError:
            db.expire_all()
            concurrent_user = db.scalar(select(User).where(User.id == identity.user_id))
            if concurrent_user is not None:
                return _synchronize_trusted_email(db, concurrent_user, identity)
            email_owner = db.scalar(select(User).where(User.email == identity.email))
            if email_owner is not None:
                raise _authentication_error() from None
            if attempt + 1 == _PROVISION_ATTEMPTS:
                raise _provider_unavailable() from None

    raise _provider_unavailable()


def actor_from_supabase_token(db: Session, token: str, settings: Settings) -> Actor:
    identity = verify_supabase_identity(token, settings)
    factory = session_factory()
    for attempt in range(_PROVISION_ATTEMPTS):
        try:
            with factory.begin() as identity_db:
                provision_supabase_user(identity_db, identity)
            break
        except IntegrityError:
            if attempt + 1 == _PROVISION_ATTEMPTS:
                raise _provider_unavailable() from None
        except SQLAlchemyError:
            raise _provider_unavailable() from None

    user = get_active_user(db, identity.user_id)
    if user is None:
        raise _authentication_error()
    return actor_for_user(db, user)

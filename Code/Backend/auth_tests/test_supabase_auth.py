from concurrent.futures import ThreadPoolExecutor
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from io import BytesIO
from json import dumps
from http.client import IncompleteRead
from threading import Barrier, local
from types import SimpleNamespace
from urllib.error import HTTPError
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy import event, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.session import session_factory
from app.domains.identity import supabase_auth
from app.domains.identity.models import User
from app.domains.identity.service import email_is_eligible


@lru_cache(maxsize=2)
def _key_pair(algorithm: str):
    if algorithm == "ES256":
        private_key = ec.generate_private_key(ec.SECP256R1())
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


class _StaticJwkClient:
    def __init__(self, public_key, kid: str):
        self.public_key = public_key
        self.kid = kid

    def get_signing_key_from_jwt(self, token: str):
        if jwt.get_unverified_header(token).get("kid") != self.kid:
            raise jwt.PyJWKClientError("unknown test key")
        return SimpleNamespace(key=self.public_key)


def test_jwks_client_is_project_derived_cached_and_timed():
    supabase_auth._jwks_client.cache_clear()
    try:
        client = supabase_auth._jwks_client("https://project.supabase.co/auth/v1")
        assert isinstance(client, supabase_auth._BoundedPyJWKClient)
        assert client.uri == "https://project.supabase.co/auth/v1/.well-known/jwks.json"
        assert client.timeout == 3
        assert client.jwk_set_cache.lifespan == 300
        assert not hasattr(client.get_signing_key, "cache_info")
        assert supabase_auth._jwks_client("https://project.supabase.co/auth/v1") is client
        assert supabase_auth._jwks_client.cache_info().maxsize == 4
    finally:
        supabase_auth._jwks_client.cache_clear()

@pytest.fixture
def sign_token(monkeypatch):
    def issue(*, algorithm="RS256", claim_overrides=None, omitted_claims=(), header_overrides=None):
        settings = get_settings()
        user_id = str(uuid4())
        private_key, public_key = _key_pair(algorithm)
        kid = f"sprint15-{algorithm.lower()}"
        monkeypatch.setattr(
            supabase_auth,
            "_jwks_client",
            lambda issuer: _StaticJwkClient(public_key, kid),
        )
        issued_at = datetime.now(UTC)
        claims = {
            "iss": settings.supabase_issuer,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": issued_at + timedelta(minutes=5),
            "iat": issued_at,
            "sub": user_id,
            "session_id": str(uuid4()),
        }
        claims.update(claim_overrides or {})
        for name in omitted_claims:
            claims.pop(name, None)
        headers = {"kid": kid} | (header_overrides or {})
        return jwt.encode(claims, private_key, algorithm=algorithm, headers=headers), user_id

    return issue


def _trusted_user(user_id: str, **overrides):
    return {
        "id": user_id,
        "is_anonymous": False,
        "identities": [{"provider": "google", "identity_data": {"email": "metadata@example.invalid"}}],
        "email": "personal@example.com",
        "email_confirmed_at": "2026-10-19T00:00:00Z",
        "user_metadata": {
            "email": "eligible@students.plm.edu.ph",
            "email_verified": True,
            "role": "service_role",
            "platform_admin": True,
            "provider": "google",
        },
        "app_metadata": {"role": "service_role", "platform_admin": True},
    } | overrides


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_verifies_es256_and_rs256_against_project_key_and_trusted_auth(
    monkeypatch, sign_token, algorithm
):
    token, user_id = sign_token(algorithm=algorithm)
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda received, settings: _trusted_user(user_id),
    )

    identity = supabase_auth.verify_supabase_identity(token, get_settings())

    assert identity == supabase_auth.VerifiedSupabaseIdentity(
        user_id=user_id,
        email="personal@example.com",
        email_verified=True,
    )
    assert not email_is_eligible(identity.email, identity.email_verified)


@pytest.mark.parametrize(
    ("claim_overrides", "omitted_claims"),
    [
        ({"iss": "https://other-project.supabase.co/auth/v1"}, ()),
        ({"aud": "anon"}, ()),
        ({"role": "service_role"}, ()),
        ({"sub": "not-a-uuid"}, ()),
        ({"session_id": "not-a-uuid"}, ()),
        ({"iat": datetime.now(UTC) + timedelta(minutes=5)}, ()),
        ({"exp": datetime.now(UTC) - timedelta(minutes=5)}, ()),
        ({}, ("session_id",)),
    ],
)
def test_rejects_bad_claims_before_auth_lookup(
    monkeypatch, sign_token, claim_overrides, omitted_claims
):
    token, _ = sign_token(claim_overrides=claim_overrides, omitted_claims=omitted_claims)
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda *args: pytest.fail("invalid claims must not trigger an Auth request"),
    )

    with pytest.raises(DomainError) as error:
        supabase_auth.verify_supabase_identity(token, get_settings())

    assert error.value.status == 401


def test_rejects_anonymous_and_token_selected_key_url(monkeypatch, sign_token):
    for claim_overrides, header_overrides in [
        ({"is_anonymous": True}, {}),
        ({}, {"jku": "https://attacker.invalid/jwks.json"}),
        ({}, {"x5u": "https://attacker.invalid/certificate"}),
    ]:
        token, _ = sign_token(claim_overrides=claim_overrides, header_overrides=header_overrides)
        monkeypatch.setattr(
            supabase_auth,
            "_trusted_auth_user",
            lambda *args: pytest.fail("rejected token must not trigger an Auth request"),
        )
        with pytest.raises(DomainError) as error:
            supabase_auth.verify_supabase_identity(token, get_settings())
        assert error.value.status == 401


def test_forged_signature_is_rejected_before_auth_lookup(monkeypatch, sign_token):
    token, _ = sign_token()
    first, second, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    forged = f"{first}.{second}.{replacement}{signature[1:]}"
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda *args: pytest.fail("forged token must not trigger an Auth request"),
    )

    with pytest.raises(DomainError) as error:
        supabase_auth.verify_supabase_identity(forged, get_settings())

    assert error.value.status == 401


def test_auth_metadata_cannot_supply_email_eligibility_or_privileges(monkeypatch, sign_token):
    token, user_id = sign_token()
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda received, settings: _trusted_user(user_id),
    )

    identity = supabase_auth.verify_supabase_identity(token, get_settings())

    assert identity.email == "personal@example.com"
    assert identity.email_verified is True
    assert not email_is_eligible(identity.email, identity.email_verified)
    assert set(identity.__dataclass_fields__) == {"user_id", "email", "email_verified"}


def test_malformed_user_metadata_is_ignored(monkeypatch, sign_token):
    token, user_id = sign_token()
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda received, settings: _trusted_user(
            user_id,
            user_metadata=["malformed", "metadata"],
            app_metadata=None,
        ),
    )

    identity = supabase_auth.verify_supabase_identity(token, get_settings())

    assert identity.email == "personal@example.com"
    assert identity.email_verified is True


def test_email_confirmation_comes_only_from_top_level_auth_field(monkeypatch, sign_token):
    token, user_id = sign_token()
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda received, settings: _trusted_user(user_id, email_confirmed_at=None),
    )

    identity = supabase_auth.verify_supabase_identity(token, get_settings())

    assert identity.email_verified is False


def test_missing_top_level_confirmation_field_is_unavailable(monkeypatch, sign_token):
    token, user_id = sign_token()
    user = _trusted_user(user_id)
    user.pop("email_confirmed_at")
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda received, settings: user,
    )

    with pytest.raises(DomainError) as error:
        supabase_auth.verify_supabase_identity(token, get_settings())

    assert error.value.status == 503


@pytest.mark.parametrize(
    "auth_user",
    [
        lambda user_id: _trusted_user(str(uuid4())),
        lambda user_id: _trusted_user(user_id, is_anonymous=True),
        lambda user_id: _trusted_user(
            user_id,
            identities=[{"provider": "facebook"}],
            user_metadata={"provider": "google"},
        ),
    ],
)
def test_rejects_auth_user_mismatch_anonymous_or_non_google_identity(
    monkeypatch, sign_token, auth_user
):
    token, user_id = sign_token()
    monkeypatch.setattr(
        supabase_auth,
        "_trusted_auth_user",
        lambda received, settings: auth_user(user_id),
    )

    with pytest.raises(DomainError) as error:
        supabase_auth.verify_supabase_identity(token, get_settings())

    assert error.value.status == 401


class _FakeResponse:
    status = 200

    def __init__(self, body: bytes = b"", read_failure: Exception | None = None):
        self.body = body
        self.read_failure = read_failure

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int):
        if self.read_failure is not None:
            raise self.read_failure
        return self.body[:limit]


def test_jwks_fetch_is_project_pinned_bounded_and_redirect_safe(monkeypatch):
    uri = "https://project.supabase.co/auth/v1/.well-known/jwks.json"
    _, public_key = _key_pair('RS256')
    key = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True) | {'kid': 'trusted-key'}
    document = dumps({'keys': [key]}).encode()
    observed = {}

    class RecordingResponse(_FakeResponse):
        def read(self, limit: int):
            observed["read_limit"] = limit
            return super().read(limit)

    class Opener:
        def open(self, request, timeout):
            observed["url"] = request.full_url
            observed["timeout"] = timeout
            return RecordingResponse(document)

    def build_test_opener(*handlers):
        observed["no_redirect"] = any(
            isinstance(handler, supabase_auth._NoRedirectHandler) for handler in handlers
        )
        return Opener()

    monkeypatch.setattr(supabase_auth, "build_opener", build_test_opener)
    client = supabase_auth._BoundedPyJWKClient(uri, timeout=3)

    assert client.fetch_data() == {"keys": [key]}
    assert observed == {
        "url": uri,
        "timeout": 3,
        "read_limit": supabase_auth._JWKS_BODY_LIMIT + 1,
        "no_redirect": True,
    }


@pytest.mark.parametrize(
    "failure",
    ["timeout", "malformed-json", "invalid-key", "oversized", "redirect", "incomplete-read"],
)
def test_jwks_fetch_failures_are_generic_503(monkeypatch, sign_token, failure):
    token, _ = sign_token()
    settings = get_settings()
    client = supabase_auth._BoundedPyJWKClient(
        f"{settings.supabase_issuer}/.well-known/jwks.json", timeout=3
    )
    observed = {"calls": 0, "no_redirect": False}

    class Opener:
        def open(self, request, timeout):
            observed["calls"] += 1
            if failure == "timeout":
                raise TimeoutError("private JWKS timeout detail")
            if failure == "redirect":
                raise HTTPError(
                    request.full_url,
                    302,
                    "private redirect detail",
                    None,
                    BytesIO(b"private redirect body"),
                )
            if failure == "incomplete-read":
                return _FakeResponse(read_failure=IncompleteRead(b"private JWKS partial body", 100))
            if failure == "oversized":
                return _FakeResponse(b"x" * (supabase_auth._JWKS_BODY_LIMIT + 1))
            if failure == "invalid-key":
                return _FakeResponse(b'{"keys":[{"kid":"not-a-usable-key"}]}')
            return _FakeResponse(b"malformed JWKS response")

    def build_test_opener(*handlers):
        observed["no_redirect"] = any(
            isinstance(handler, supabase_auth._NoRedirectHandler) for handler in handlers
        )
        return Opener()

    monkeypatch.setattr(supabase_auth, "build_opener", build_test_opener)
    monkeypatch.setattr(supabase_auth, "_jwks_client", lambda issuer: client)

    with pytest.raises(DomainError) as error:
        supabase_auth.verify_supabase_identity(token, settings)

    assert error.value.status == 503
    assert error.value.message == "Authentication is temporarily unavailable."
    assert all(
        detail not in str(error.value)
        for detail in (
            "private JWKS timeout detail",
            "private redirect detail",
            "private redirect body",
            "private JWKS partial body",
        )
    )
    assert observed == {"calls": 1, "no_redirect": True}
    assert client.jwk_set_cache.get() is None


def test_auth_fetch_uses_configured_project_key_timeout_and_no_redirects(monkeypatch):
    settings = get_settings()
    body = b'{"id":"trusted-user"}'
    observed = {}

    class Opener:
        def open(self, request, timeout):
            observed["url"] = request.full_url
            observed["apikey"] = request.get_header("Apikey")
            observed["authorization"] = request.get_header("Authorization")
            observed["timeout"] = timeout
            return _FakeResponse(body)

    def build_test_opener(*handlers):
        observed["no_redirect"] = any(
            isinstance(handler, supabase_auth._NoRedirectHandler) for handler in handlers
        )
        return Opener()

    monkeypatch.setattr(supabase_auth, "build_opener", build_test_opener)

    result = supabase_auth._trusted_auth_user("test-access-token", settings)

    assert result == {"id": "trusted-user"}
    assert observed == {
        "url": f"{settings.supabase_issuer}/user",
        "apikey": settings.supabase_publishable_key,
        "authorization": "Bearer test-access-token",
        "timeout": 3,
        "no_redirect": True,
    }


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("private timeout detail"), b"not-json", IncompleteRead(b"private partial body", 64),
     b'[' * 2000 + b'0' + b']' * 2000],
    ids=["timeout", "malformed-json", "incomplete-read", "deeply-nested-json"],
)
def test_auth_timeout_and_malformed_response_are_generic_503(monkeypatch, failure):
    class Opener:
        def open(self, request, timeout):
            if isinstance(failure, IncompleteRead):
                return _FakeResponse(read_failure=failure)
            if isinstance(failure, Exception):
                raise failure
            return _FakeResponse(failure)

    monkeypatch.setattr(supabase_auth, "build_opener", lambda *handlers: Opener())

    with pytest.raises(DomainError) as error:
        supabase_auth._trusted_auth_user("test-access-token", get_settings())

    assert error.value.status == 503
    assert error.value.message == "Authentication is temporarily unavailable."
    assert "private timeout detail" not in str(error.value)
    assert "private partial body" not in str(error.value)


def test_auth_redirect_is_not_followed_or_disclosed(monkeypatch):
    observed = {"calls": 0, "no_redirect": False}

    class Opener:
        def open(self, request, timeout):
            observed["calls"] += 1
            raise HTTPError(
                request.full_url,
                302,
                "redirect detail",
                None,
                BytesIO(b"private response body"),
            )

    def build_test_opener(*handlers):
        observed["no_redirect"] = any(
            isinstance(handler, supabase_auth._NoRedirectHandler) for handler in handlers
        )
        return Opener()

    monkeypatch.setattr(supabase_auth, "build_opener", build_test_opener)

    with pytest.raises(DomainError) as error:
        supabase_auth._trusted_auth_user("test-access-token", get_settings())

    assert error.value.status == 503
    assert observed == {"calls": 1, "no_redirect": True}
    assert "private response body" not in error.value.message


def test_auth_401_is_reported_as_generic_invalid_credentials(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(
                request.full_url,
                401,
                "private auth detail",
                None,
                BytesIO(b"private response body"),
            )

    monkeypatch.setattr(supabase_auth, "build_opener", lambda *handlers: Opener())

    with pytest.raises(DomainError) as error:
        supabase_auth._trusted_auth_user("test-access-token", get_settings())

    assert error.value.status == 401
    assert "private auth detail" not in error.value.message
    assert "private response body" not in error.value.message


def test_auth_response_body_is_bounded(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            return _FakeResponse(b"x" * (supabase_auth._AUTH_BODY_LIMIT + 1))

    monkeypatch.setattr(supabase_auth, "build_opener", lambda *handlers: Opener())

    with pytest.raises(DomainError) as error:
        supabase_auth._trusted_auth_user("test-access-token", get_settings())

    assert error.value.status == 503


def test_new_user_has_no_profile_grants_or_admin_privilege(db):
    identity = supabase_auth.VerifiedSupabaseIdentity(
        user_id=str(uuid4()), email="personal@example.com", email_verified=True
    )

    user = supabase_auth.provision_supabase_user(db, identity)

    assert user.id == identity.user_id
    assert user.email == identity.email and user.email_verified is True
    assert user.nickname is None and user.age_bracket is None and user.tags == []
    assert user.persona_visible is False and user.platform_admin is False
    from app.domains.organizations.models import OrgMembership
    assert db.scalar(select(func.count()).select_from(OrgMembership).where(OrgMembership.user_id == user.id)) == 0


def test_different_subject_cannot_claim_existing_email(db, make_user):
    existing = make_user(email="claimed@example.com")
    identity = supabase_auth.VerifiedSupabaseIdentity(
        user_id=str(uuid4()), email=existing.email, email_verified=True
    )

    with pytest.raises(DomainError) as error:
        supabase_auth.provision_supabase_user(db, identity)

    assert error.value.status == 401
    assert db.scalar(select(User).where(User.email == existing.email)).id == existing.id


def test_email_sync_preserves_profile_grants_admin_and_inactive_state(
    db, make_user, make_org
):
    from app.domains.organizations.models import OrgMembership

    user = make_user(
        email="old@students.plm.edu.ph",
        nickname="Preserved nickname",
        age_bracket="25-34",
        tags=["music", "walking"],
        pronouns="they/them",
        icebreaker="Preserved prompt",
        persona_visible=True,
        active=False,
        platform_admin=True,
    )
    organization = make_org(owner=user)
    identity = supabase_auth.VerifiedSupabaseIdentity(
        user_id=user.id, email="updated@example.com", email_verified=False
    )

    updated = supabase_auth.provision_supabase_user(db, identity)

    membership = db.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == organization.id,
        )
    )
    assert updated.email == identity.email and updated.email_verified is False
    assert updated.active is False and updated.platform_admin is True
    assert (updated.nickname, updated.age_bracket, updated.tags) == (
        "Preserved nickname",
        "25-34",
        ["music", "walking"],
    )
    assert (updated.pronouns, updated.icebreaker, updated.persona_visible) == (
        "they/them",
        "Preserved prompt",
        True,
    )
    assert membership is not None and membership.role == "owner" and membership.active is True


def test_inactive_account_remains_denied_after_trusted_email_sync(db, make_user, monkeypatch):
    user = make_user(email="old@example.invalid", active=False, platform_admin=True)
    identity = supabase_auth.VerifiedSupabaseIdentity(
        user_id=user.id, email="new@example.com", email_verified=True
    )
    monkeypatch.setattr(
        supabase_auth,
        "verify_supabase_identity",
        lambda token, settings: identity,
    )

    with pytest.raises(DomainError) as error:
        supabase_auth.actor_from_supabase_token(db, "synthetic-token", get_settings())

    db.refresh(user)
    assert error.value.status == 401
    assert user.email == identity.email and user.email_verified is True
    assert user.active is False and user.platform_admin is True


def test_invalid_token_creates_no_user_row(db):
    with pytest.raises(DomainError) as error:
        supabase_auth.actor_from_supabase_token(db, "not-a-jwt", get_settings())

    assert error.value.status == 401
    assert db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize('deep_header', [False, True])
def test_deeply_nested_attacker_jwt_is_generic_401_before_network(monkeypatch, deep_header):
    nested = b'[' * 2000 + b'0' + b']' * 2000
    header = b'{"alg":"RS256","kid":"test"}'
    payload = nested
    if deep_header:
        header = b'{"alg":"RS256","kid":"test","extra":' + nested + b'}'
        payload = b'{}'
    encode = lambda value: urlsafe_b64encode(value).rstrip(b'=').decode('ascii')
    token = encode(header) + '.' + encode(payload) + '.c2ln'
    jwks = jwt.PyJWKClient('https://sprint15-test.supabase.co/auth/v1/.well-known/jwks.json')
    def forbidden_fetch():
        pytest.fail('Malformed deeply nested JWT must not fetch a signing key')
    monkeypatch.setattr(jwks, 'fetch_data', forbidden_fetch)
    monkeypatch.setattr(supabase_auth, '_jwks_client', lambda issuer: jwks)
    with pytest.raises(DomainError) as error:
        supabase_auth.verify_supabase_identity(token, get_settings())
    assert error.value.status == 401
    assert error.value.message == 'Authentication could not be verified.'


def test_concurrent_onboarding_conflict_creates_one_identity(db):
    identity = supabase_auth.VerifiedSupabaseIdentity(
        user_id=str(uuid4()), email="race@example.com", email_verified=True
    )
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    start = Barrier(2)
    thread_state = local()

    def synchronize_after_initial_lookup(connection, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.lower().split())
        if (
            not getattr(thread_state, "waited", False)
            and "from users" in normalized
            and "users.id =" in normalized
        ):
            thread_state.waited = True
            start.wait(timeout=10)

    event.listen(db.get_bind(), "after_cursor_execute", synchronize_after_initial_lookup)
    try:
        def onboard():
            with factory.begin() as identity_db:
                user = supabase_auth.provision_supabase_user(identity_db, identity)
                return user.id

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: onboard(), range(2)))
    finally:
        event.remove(db.get_bind(), "after_cursor_execute", synchronize_after_initial_lookup)

    with factory() as check_db:
        users = check_db.scalars(select(User).where(User.id == identity.user_id)).all()
    assert results == [identity.user_id, identity.user_id]
    assert len(users) == 1

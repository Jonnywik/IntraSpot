import ipaddress
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


def _is_public_https_root(value: str) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if (parsed.scheme != 'https' or not host or parsed.username is not None
            or parsed.password is not None or port is not None
            or parsed.path or parsed.query or parsed.fragment):
        return False
    host = host.casefold()
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return bool(re.fullmatch(
        r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', host
    ))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env.local', extra='ignore', hide_input_in_errors=True)
    environment: Literal['local', 'test', 'production', 'hosted'] = 'production'
    fixture_auth: bool = False
    auth_provider: Literal['fixture', 'supabase'] = 'fixture'
    database_url: str = Field(repr=False)
    migration_database_url: str | None = Field(default=None, repr=False)
    media_root: Path = ROOT / '.local/media'
    supabase_url: str | None = None
    supabase_publishable_key: str | None = Field(default=None, repr=False)
    public_api_url: str | None = None
    jwt_issuer: str = 'urn:intraspot:local'
    jwt_audience: str = 'intraspot-api'
    jwt_public_key_file: Path = ROOT / '.local/public.pem'
    cors_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:3000']

    @model_validator(mode='after')
    def validate_local_boundary(self):
        if self.environment == 'hosted':
            self._validate_hosted_boundary()
            return self
        if self.environment not in {'local', 'test'}:
            raise ValueError('Only isolated local/test development is enabled; production is disabled')
        url = make_url(self.database_url)
        if url.drivername != 'postgresql+psycopg' or url.host not in {'127.0.0.1', 'localhost'} or url.port != 5433:
            raise ValueError('MVP database must be isolated loopback PostgreSQL on port 5433')
        if self.auth_provider == 'fixture':
            if not self.fixture_auth or url.database not in {'intraspot_mvp', 'intraspot_mvp_test'}:
                raise ValueError('Fixture auth requires its isolated fictional development/test database')
            if self.supabase_url or self.supabase_publishable_key:
                raise ValueError('Real provider configuration must not be mixed with fictional auth')
            allowed_origins = {'http://localhost:3000', 'http://127.0.0.1:3000'}
            if not self.jwt_public_key_file.is_file():
                raise ValueError('Run local_setup to generate local signing keys')
        else:
            expected_database = 'intraspot_real_dev_test' if self.environment == 'test' else 'intraspot_real_dev'
            if self.fixture_auth or url.database != expected_database:
                raise ValueError('Supabase auth requires fixture auth disabled and its separate real-development database')
            if not self.supabase_url or not re.fullmatch(r'https://[a-z0-9-]{8,64}\.supabase\.co', self.supabase_url):
                raise ValueError('Configure one HTTPS Supabase development project URL without a path or credentials')
            if not self.supabase_publishable_key or not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]{10,256}', self.supabase_publishable_key):
                raise ValueError('Use the public Supabase publishable key, never an admin key or legacy token')
            allowed_origins = {'http://localhost:3001', 'http://127.0.0.1:3001'}
        if not self.cors_origins or any(x not in allowed_origins for x in self.cors_origins):
            raise ValueError('Only explicit localhost frontend origins are supported')
        if not self.media_root.is_absolute():
            raise ValueError('The local media root must be absolute')
        self.media_root = self.media_root.resolve() / (
            'real' if self.auth_provider == 'supabase' else 'fixture'
        ) / self.environment
        return self

    def _validate_hosted_boundary(self):
        if self.auth_provider != 'supabase' or self.fixture_auth:
            raise ValueError('Hosted configuration requires Supabase auth with fixture auth disabled')
        supabase_match = re.fullmatch(
            r'https://([a-z0-9-]{8,64})\.supabase\.co', self.supabase_url or ''
        )
        if not supabase_match:
            raise ValueError('Configure one HTTPS Supabase project URL without a path or credentials')
        if not self.supabase_publishable_key or not re.fullmatch(
            r'sb_publishable_[A-Za-z0-9_-]{10,256}', self.supabase_publishable_key
        ):
            raise ValueError('Use the public Supabase publishable key, never an admin key or legacy token')
        if not self.public_api_url or not _is_public_https_root(self.public_api_url):
            raise ValueError('Configure the public API as one exact HTTPS origin')
        if (not self.cors_origins or len(set(self.cors_origins)) != len(self.cors_origins)
                or any(not _is_public_https_root(origin) for origin in self.cors_origins)):
            raise ValueError('Hosted CORS requires exact public HTTPS frontend origins')

        try:
            url = make_url(self.database_url)
        except (ArgumentError, TypeError, ValueError):
            raise ValueError('Configure a valid hosted PostgreSQL pooler URL') from None
        host = (url.host or '').casefold()
        username = (url.username or '').casefold()
        runtime_role, separator, runtime_project_ref = username.rpartition('.')
        project_ref = supabase_match.group(1)
        if (url.drivername != 'postgresql+psycopg'
                or not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.pooler\.supabase\.com', host)
                or url.port != 5432 or url.database != 'postgres'
                or not url.password):
            raise ValueError('Hosted PostgreSQL must use the Supabase session pooler on port 5432 and database postgres')
        if (not separator or runtime_project_ref != project_ref
                or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,62}', runtime_role)
                or any(name in runtime_role for name in ('postgres', 'admin', 'service_role'))):
            raise ValueError('Hosted runtime database credentials must use a named non-admin role')
        sslmode = url.query.get('sslmode')
        sslrootcert = url.query.get('sslrootcert')
        if (sslmode != 'verify-full' or not isinstance(sslrootcert, str)
                or not Path(sslrootcert).is_absolute() or not Path(sslrootcert).is_file()):
            raise ValueError('Hosted PostgreSQL requires sslmode=verify-full and an existing CA file')
        if self.migration_database_url:
            try:
                migration_url = make_url(self.migration_database_url)
            except (ArgumentError, TypeError, ValueError):
                raise ValueError('Configure a valid hosted migration PostgreSQL URL') from None
            migration_host = (migration_url.host or '').casefold()
            migration_username = (migration_url.username or '').casefold()
            migration_role, migration_separator, migration_project_ref = migration_username.rpartition('.')
            if (migration_url.drivername != 'postgresql+psycopg'
                    or migration_host != host or migration_url.port != 5432
                    or migration_url.database != 'postgres' or not migration_url.password
                    or migration_username == username or not migration_separator
                    or migration_project_ref != project_ref
                    or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,62}', migration_role)
                    or any(name in migration_role for name in ('postgres', 'admin', 'service_role'))
                    or migration_url.query.get('sslmode') != 'verify-full'
                    or migration_url.query.get('sslrootcert') != sslrootcert):
                raise ValueError('Migration credentials must be separate, project-matched, and use the same verified TLS endpoint')
        if not self.media_root.is_absolute():
            raise ValueError('The media root must be absolute')

    @property
    def supabase_issuer(self) -> str:
        if self.auth_provider != 'supabase' or not self.supabase_url:
            raise ValueError('Supabase identity is not configured')
        return self.supabase_url + '/auth/v1'


@lru_cache
def get_settings():
    profile = os.environ.get('INTRASPOT_CONFIG')
    if profile == 'hosted':
        return Settings(_env_file=None, environment='hosted')
    if profile is not None:
        if profile != 'real' or not (ROOT / '.env.real.local').is_file():
            raise ValueError('The requested isolated development configuration is unavailable')
        return Settings(_env_file=ROOT / '.env.real.local')
    return Settings()

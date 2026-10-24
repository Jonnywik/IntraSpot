import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env.local', extra='ignore', hide_input_in_errors=True)
    environment: Literal['local', 'test', 'production'] = 'production'
    fixture_auth: bool = False
    auth_provider: Literal['fixture', 'supabase'] = 'fixture'
    database_url: str = Field(repr=False)
    media_root: Path = ROOT / '.local/media'
    supabase_url: str | None = None
    supabase_publishable_key: str | None = Field(default=None, repr=False)
    jwt_issuer: str = 'urn:intraspot:local'
    jwt_audience: str = 'intraspot-api'
    jwt_public_key_file: Path = ROOT / '.local/public.pem'
    cors_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:3000']

    @model_validator(mode='after')
    def validate_local_boundary(self):
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

    @property
    def supabase_issuer(self) -> str:
        if self.auth_provider != 'supabase' or not self.supabase_url:
            raise ValueError('Supabase identity is not configured')
        return self.supabase_url + '/auth/v1'


@lru_cache
def get_settings():
    profile = os.environ.get('INTRASPOT_CONFIG')
    if profile is not None:
        if profile != 'real' or not (ROOT / '.env.real.local').is_file():
            raise ValueError('The requested isolated development configuration is unavailable')
        return Settings(_env_file=ROOT / '.env.real.local')
    return Settings()

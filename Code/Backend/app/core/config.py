from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env.local', extra='ignore')
    environment: Literal['local', 'test', 'production'] = 'production'
    fixture_auth: bool = False
    database_url: str
    jwt_issuer: str = 'urn:intraspot:local'
    jwt_audience: str = 'intraspot-api'
    jwt_public_key_file: Path = ROOT / '.local/public.pem'
    cors_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:3000']

    @model_validator(mode='after')
    def validate_local_boundary(self):
        if self.environment not in {'local', 'test'} or not self.fixture_auth:
            raise ValueError('This MVP supports explicit local/test fixture auth only; production is disabled')
        url = make_url(self.database_url)
        if url.drivername != 'postgresql+psycopg' or url.host not in {'127.0.0.1', 'localhost'} or url.port != 5433:
            raise ValueError('MVP database must be isolated loopback PostgreSQL on port 5433')
        if url.database not in {'intraspot_mvp', 'intraspot_mvp_test'}:
            raise ValueError('MVP database target is not allowlisted')
        if not self.cors_origins or any(x not in {'http://localhost:3000', 'http://127.0.0.1:3000'} for x in self.cors_origins):
            raise ValueError('Only explicit localhost frontend origins are supported')
        if not self.jwt_public_key_file.is_file():
            raise ValueError('Run local_setup to generate local signing keys')
        return self


@lru_cache
def get_settings():
    return Settings()

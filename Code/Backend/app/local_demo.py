"""Read fixed, offline-issued fixture credentials on loopback only; never issue tokens."""
import json
from ipaddress import ip_address

import jwt
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.core.config import ROOT, get_settings
from app.core.errors import DomainError
from app.local_identities import ACCOUNTS, fixture_id

router = APIRouter()
CATALOG_PATH = ROOT / '.local/accounts.json'


class LocalDemoAccount(BaseModel):
    label: str
    token: str


@router.get('/local-demo/accounts', response_model=list[LocalDemoAccount], tags=['local-demo'])
def accounts(request: Request, response: Response):
    settings = get_settings()
    try:
        local_peer = request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        local_peer = False
    origin = request.headers.get('origin')
    if (
        settings.environment != 'local' or not settings.fixture_auth or not local_peer
        or request.url.hostname not in {'localhost', '127.0.0.1', '::1'}
        or (origin is not None and origin not in settings.cors_origins)
    ):
        raise DomainError('local_demo_unavailable', 'The fictional account catalog is available only in explicit local mode.', 404)
    try:
        rows = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
        expected = {label: fixture_id(label) for label, _, _ in ACCOUNTS}
        if not isinstance(rows, list) or len(rows) != len(expected):
            raise ValueError('invalid fixture catalog')
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {'label', 'token'}:
                raise ValueError('invalid fixture entry')
            label = row['label']
            if label not in expected or label in seen:
                raise ValueError('unexpected fixture identity')
            claims = jwt.decode(row['token'], settings.jwt_public_key_file.read_bytes(),
                                algorithms=['RS256'], issuer=settings.jwt_issuer,
                                audience=settings.jwt_audience,
                                options={'require': ['sub', 'exp', 'iss', 'aud']})
            if claims['sub'] != expected[label]:
                raise ValueError('fixture subject mismatch')
            seen.add(label)
    except (OSError, ValueError, TypeError, KeyError, jwt.PyJWTError):
        raise DomainError('local_demo_catalog_not_ready',
                          'Renew the fixed fictional accounts with the local identity setup command, then retry.', 503) from None
    response.headers['Cache-Control'] = 'no-store'
    return rows

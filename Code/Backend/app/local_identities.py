"""Fixed local-only fictional identities; no login endpoint or later-domain writes."""
import json
import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

import jwt
from sqlalchemy.engine import make_url

from app.core.config import ROOT, get_settings
from app.db.models import now
from app.db.session import session_factory
from app.domains.identity.models import User


ACCOUNTS = tuple((f'Fictional student {i}', f'student{i}@students.plm.edu.ph', False) for i in range(1, 11)) + (
    ('Fictional faculty', 'faculty@faculty.plm.edu.ph', False),
    ('Fictional organizer', 'organizer@plm.edu.ph', False),
    ('Fictional platform admin', 'platform-admin@plm.edu.ph', True),
    ('Fictional visitor (not PLM)', 'visitor@example.invalid', False),
    ('Fictional incomplete profile', 'new-student@students.plm.edu.ph', False),
)


def fixture_id(label):
    return str(uuid5(NAMESPACE_URL, f'intraspot-local:{label}'))


def ensure_users(db):
    for label, email, platform_admin in ACCOUNTS:
        existing = db.get(User, fixture_id(label))
        if existing is not None:
            if existing.email != email:
                raise RuntimeError('Fictional fixture identity collision; no identities were overwritten')
            continue
        incomplete = label == 'Fictional incomplete profile'
        db.add(User(id=fixture_id(label), email=email, email_verified=True, active=True,
                    platform_admin=platform_admin, nickname=None if incomplete else label,
                    age_bracket=None if incomplete else '18-24', tags=[] if incomplete else ['community'],
                    persona_visible=False))


def main():
    settings = get_settings()
    if settings.environment != 'local' or not settings.fixture_auth or make_url(settings.database_url).database != 'intraspot_mvp':
        raise RuntimeError('Identity fixture command requires explicit local mode and the development MVP database')
    if len(sys.argv) != 1:
        raise RuntimeError('This command accepts no account or subject arguments')
    private_key = (ROOT / '.local/private.pem').read_bytes()
    with session_factory()() as db, db.begin():
        ensure_users(db)
    issued = now()
    manifest = [{'label': label, 'token': jwt.encode(
        {'sub': fixture_id(label), 'iss': settings.jwt_issuer, 'aud': settings.jwt_audience,
         'iat': issued, 'exp': issued + timedelta(hours=8)}, private_key, algorithm='RS256',
        headers={'kid': 'local-fixture'})} for label, _, _ in ACCOUNTS]
    output = ROOT / '.local/accounts.json'
    output.write_text(json.dumps(manifest), encoding='utf-8')
    print(f'{len(manifest)} predefined fictional identities ready; ignored Backend/.local/accounts.json. Tokens expire in 8 hours.')


if __name__ == '__main__':
    main()

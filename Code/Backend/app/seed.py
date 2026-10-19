"""Idempotent fictional fixtures; no credentials printed and no database reset."""
import json
from datetime import timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import jwt
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import ROOT, get_settings
from app.db.models import now
from app.db.session import session_factory


def fixture_id(label):
    return str(uuid5(NAMESPACE_URL, f'intraspot-local:{label}'))


def main():
    settings = get_settings()
    if (settings.environment != 'local' or settings.auth_provider != 'fixture'
            or not settings.fixture_auth or make_url(settings.database_url).database != 'intraspot_mvp'):
        raise RuntimeError('Seed is local-only; test fixtures use the separate test database')
    from app.domains.identity.models import User
    from app.domains.organizations.models import Organization, OrgMembership
    from app.domains.events.models import Event
    from app.domains.registrations.models import Registration
    accounts = [(f'Fictional student {i}', f'student{i}@students.plm.edu.ph', False) for i in range(1, 11)]
    accounts += [('Fictional faculty', 'faculty@faculty.plm.edu.ph', False),
                 ('Fictional organizer', 'organizer@plm.edu.ph', False),
                 ('Fictional platform admin', 'platform-admin@plm.edu.ph', True),
                 ('Fictional visitor (not PLM)', 'visitor@example.invalid', False),
                 ('Fictional incomplete profile', 'new-student@students.plm.edu.ph', False)]
    with session_factory()() as db, db.begin():
        for label, email, platform_admin in accounts:
            user_id = fixture_id(label)
            if db.get(User, user_id) is None:
                incomplete = label == 'Fictional incomplete profile'
                db.add(User(id=user_id, email=email, email_verified=True, active=True, platform_admin=platform_admin,
                            nickname=None if incomplete else label, age_bracket=None if incomplete else '18-24',
                            tags=[] if incomplete else ['community'], persona_visible=False))
        db.flush()
        owner = fixture_id('Fictional organizer')
        org_id = fixture_id('creative-society')
        if db.get(Organization, org_id) is None:
            db.add(Organization(id=org_id, name='PLM Creative Society', description='A fictional recognized student organization.',
                                accreditation_status='approved', created_by=owner))
        pending_id = fixture_id('heritage-society')
        if db.get(Organization, pending_id) is None:
            db.add(Organization(id=pending_id, name='PLM Heritage Society', description='A fictional organization awaiting offline assessment.',
                                accreditation_status='pending', created_by=owner))
        db.flush()
        for organization, label, role in [(org_id, 'Fictional organizer', 'owner'), (pending_id, 'Fictional organizer', 'owner'),
                                           (org_id, 'Fictional student 1', 'member'), (org_id, 'Fictional faculty', 'member')]:
            user_id = fixture_id(label)
            if db.scalar(select(OrgMembership).where(OrgMembership.org_id == organization, OrgMembership.user_id == user_id)) is None:
                db.add(OrgMembership(id=fixture_id(f'grant:{organization}:{label}'), org_id=organization, user_id=user_id, role=role, active=True))
        events = [('heritage-gathering', 'Stories within the walls', 'Meet your campus community through shared stories.', 'heritage', 18),
                  ('design-jam', 'Campus Design Jam', 'An afternoon of ideas, sketches and new connections.', 'design', 24),
                  ('garden-day', 'Campus Garden Day', 'Grow a greener campus together.', 'garden', 1)]
        for index, (slug, title, summary, banner, capacity) in enumerate(events):
            if db.get(Event, fixture_id(slug)) is None:
                start = now() + timedelta(days=7 + index, hours=1)
                db.add(Event(id=fixture_id(slug), org_id=org_id, created_by=owner, title=title, summary=summary,
                             description=f'{summary} This event is fictional and exists only for local MVP testing.',
                             starts_at=start, ends_at=start + timedelta(hours=2), venue_name='PLM courtyard',
                             venue_address='Intramuros, Manila', capacity=capacity, banner_key=banner, cost_label='Free',
                             status='published', published_at=now(), registration_mode='instant', event_type='scheduled',
                             next_admission=1 if slug == 'garden-day' else 0, interest_count=12))
        db.flush()
        full_registration = fixture_id('seed-confirmed')
        if db.get(Registration, full_registration) is None:
            db.add(Registration(id=full_registration, event_id=fixture_id('garden-day'), user_id=fixture_id('Fictional student 10'),
                                status='confirmed', admission_order=1, confirmed_at=now()))
    private_key = (ROOT / '.local/private.pem').read_bytes()
    issued = now()
    manifest = [{'label': label, 'token': jwt.encode({'sub': fixture_id(label), 'iss': settings.jwt_issuer,
                 'aud': settings.jwt_audience, 'iat': issued, 'exp': issued + timedelta(hours=8)}, private_key,
                 algorithm='RS256', headers={'kid': 'local-fixture'})} for label, _, _ in accounts]
    output = ROOT.parent / 'Frontend/public/local-accounts.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(manifest), encoding='utf-8')
    (ROOT / '.local/fixture-ids.json').write_text(json.dumps({slug: fixture_id(slug) for slug in
        ['creative-society', 'heritage-society', 'heritage-gathering', 'design-jam', 'garden-day']}, indent=2), encoding='utf-8')
    print(f'Seed complete: {len(accounts)} fictional accounts; ignored manifest at Code/Frontend/public/local-accounts.json. Tokens expire in 8 hours.')


if __name__ == '__main__':
    main()

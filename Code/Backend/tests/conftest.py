"""Shared PostgreSQL fixtures; resets are confined to the named test database."""
import os
from datetime import timedelta

import jwt
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import ROOT, Settings, get_settings
from app.db.models import now, uid
from app.db.session import Base, engine

local_settings = Settings()
test_url = make_url(local_settings.database_url).set(database='intraspot_mvp_test')
os.environ['ENVIRONMENT'] = 'test'
os.environ['FIXTURE_AUTH'] = 'true'
os.environ['DATABASE_URL'] = test_url.render_as_string(hide_password=False)
get_settings.cache_clear()
engine.cache_clear()


def assert_test_target():
    url = make_url(get_settings().database_url)
    assert url.database == 'intraspot_mvp_test' and url.host in {'127.0.0.1', 'localhost'} and url.port == 5433


@pytest.fixture(scope='session', autouse=True)
def migrated_test_database():
    assert_test_target()
    admin = create_engine(local_settings.database_url, isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname='intraspot_mvp_test'")):
            connection.execute(text('CREATE DATABASE intraspot_mvp_test'))
    admin.dispose()
    command.upgrade(Config(str(ROOT / 'alembic.ini')), 'head')
    yield
    engine().dispose()


@pytest.fixture(autouse=True)
def clean_test_database(migrated_test_database):
    assert_test_target()
    # ORM metadata names only; never user input and never the development database.
    tables = ','.join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine().begin() as connection:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
        connection.execute(text(f'TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE'))


@pytest.fixture
def db():
    with Session(engine(), expire_on_commit=False) as session:
        yield session
        session.rollback()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def make_user(db):
    from app.domains.identity.models import User
    def factory(**fields):
        defaults = {'id': uid(), 'email': f'fictional-{uid()}@students.plm.edu.ph', 'email_verified': True,
                    'nickname': 'Fictional attendee', 'age_bracket': '18-24', 'tags': ['arts'], 'active': True,
                    'platform_admin': False, 'persona_visible': False}
        user = User(**(defaults | fields))
        db.add(user)
        db.commit()
        return user
    return factory


@pytest.fixture
def make_org(db, make_user):
    from app.domains.organizations.models import Organization, OrgMembership
    def factory(owner=None, **fields):
        owner = owner or make_user()
        org = Organization(**({'id': uid(), 'name': 'Fictional society', 'description': 'Local test organization',
                               'accreditation_status': 'approved', 'created_by': owner.id} | fields))
        db.add(org)
        db.flush()
        db.add(OrgMembership(id=uid(), org_id=org.id, user_id=owner.id, role='owner', active=True))
        db.commit()
        return org
    return factory


@pytest.fixture
def make_event(db, make_org):
    from app.domains.events.models import Event
    def factory(org=None, **fields):
        org = org or make_org()
        event = Event(**({'id': uid(), 'org_id': org.id, 'created_by': org.created_by, 'title': 'Fictional campus gathering',
                          'summary': '', 'description': 'A fictional local demonstration.', 'starts_at': now() + timedelta(days=2),
                          'ends_at': now() + timedelta(days=2, hours=2), 'venue_name': 'PLM courtyard',
                          'venue_address': 'Intramuros, Manila', 'capacity': 3, 'banner_key': 'heritage', 'cost_label': 'Free',
                          'status': 'published', 'registration_mode': 'instant', 'event_type': 'scheduled',
                          'published_at': now(), 'next_admission': 0, 'interest_count': 0} | fields))
        db.add(event)
        db.commit()
        return event
    return factory


@pytest.fixture
def token_for():
    private_key = (ROOT / '.local/private.pem').read_bytes()
    def factory(user_or_id, **claim_overrides):
        subject = user_or_id.id if hasattr(user_or_id, 'id') else user_or_id
        settings = get_settings()
        claims = {'sub': subject, 'iss': settings.jwt_issuer, 'aud': settings.jwt_audience,
                  'iat': now(), 'exp': now() + timedelta(minutes=30)} | claim_overrides
        return jwt.encode(claims, private_key, algorithm='RS256', headers={'kid': 'local-fixture'})
    return factory

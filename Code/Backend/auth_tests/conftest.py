"""Real-auth protocol tests use fictional identities in their own serial database."""
import os
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import ROOT, Settings, get_settings
from app.db.models import now, uid
from app.db.session import engine

base_settings = Settings()
assert base_settings.auth_provider == 'fixture'
test_url = make_url(base_settings.database_url).set(database='intraspot_real_dev_test')
os.environ.pop('INTRASPOT_CONFIG', None)
os.environ.update({
    'ENVIRONMENT': 'test', 'AUTH_PROVIDER': 'supabase', 'FIXTURE_AUTH': 'false',
    'DATABASE_URL': test_url.render_as_string(hide_password=False),
    'SUPABASE_URL': 'https://sprint15-test.supabase.co',
    'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_sprint15_fictional_key',
    'CORS_ORIGINS': '["http://localhost:3001","http://127.0.0.1:3001"]',
})
get_settings.cache_clear()
engine.cache_clear()


def assert_test_target():
    target = make_url(get_settings().database_url)
    assert target.database == 'intraspot_real_dev_test'
    assert target.host in {'127.0.0.1', 'localhost'} and target.port == 5433
    assert get_settings().auth_provider == 'supabase' and not get_settings().fixture_auth


@pytest.fixture(scope='session', autouse=True)
def migrated_auth_database():
    assert_test_target()
    administrator = create_engine(base_settings.database_url, isolation_level='AUTOCOMMIT')
    with administrator.connect() as connection:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp'
        if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname='intraspot_real_dev_test'")):
            connection.execute(text('CREATE DATABASE intraspot_real_dev_test'))
    administrator.dispose()
    command.upgrade(Config(str(ROOT / 'alembic.ini')), 'head')
    yield
    engine().dispose()


@pytest.fixture(autouse=True)
def clean_auth_database(migrated_auth_database):
    from app.db.session import Base
    assert_test_target()
    tables = ','.join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
    with engine().begin() as connection:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_real_dev_test'
        connection.execute(text('TRUNCATE TABLE ' + tables + ' RESTART IDENTITY CASCADE'))


@pytest.fixture
def db():
    with Session(engine(), expire_on_commit=False) as connection:
        yield connection
        connection.rollback()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as connection:
        yield connection


@pytest.fixture
def make_user(db):
    from app.domains.identity.models import User
    def create(**values):
        user = User(**({'id': uid(), 'email': uid() + '@example.invalid',
                       'email_verified': True, 'nickname': None, 'age_bracket': None,
                       'tags': [], 'active': True, 'platform_admin': False,
                       'persona_visible': False} | values))
        db.add(user)
        db.commit()
        return user
    return create


@pytest.fixture
def make_org(db, make_user):
    from app.domains.organizations.models import Organization, OrgMembership
    def create(owner=None, **values):
        owner = owner or make_user(email=uid() + '@plm.edu.ph')
        organization = Organization(**({'id': uid(), 'name': 'Fictional real-auth test club',
            'description': 'Only fictional protocol fixtures.', 'accreditation_status': 'approved',
            'created_by': owner.id} | values))
        db.add(organization)
        db.flush()
        db.add(OrgMembership(id=uid(), org_id=organization.id, user_id=owner.id, role='owner', active=True))
        db.commit()
        return organization
    return create


@pytest.fixture
def make_event(db, make_org):
    from app.domains.events.models import Event
    def create(org=None, **values):
        org = org or make_org()
        event = Event(**({'id': uid(), 'org_id': org.id, 'created_by': org.created_by,
            'title': 'Fictional authentication check', 'summary': '', 'description': 'No real attendees.',
            'starts_at': now() + timedelta(days=2), 'ends_at': now() + timedelta(days=2, hours=1),
            'venue_name': 'Fictional hall', 'venue_address': 'Fictional campus', 'capacity': 3,
            'banner_key': 'heritage', 'cost_label': 'Free', 'status': 'published',
            'registration_mode': 'instant', 'event_type': 'scheduled', 'published_at': now(),
            'next_admission': 0, 'interest_count': 0} | values))
        db.add(event)
        db.commit()
        return event
    return create

"""Role changes run only inside a rolled-back disposable database transaction."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import engine
from app.hosted_security import harden, identifier


def test_runtime_and_browser_roles_cannot_bypass_application_boundary(db):
    suffix = uuid4().hex[:12]
    runtime, owner = 's25_app_' + suffix, 's25_owner_' + suffix
    with engine().connect() as connection, connection.begin() as transaction:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
        for name in (runtime, owner):
            connection.execute(text(f'CREATE ROLE {identifier(name)} NOLOGIN'))
        for name in ('anon', 'authenticated'):
            if not connection.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:name'), {'name': name}):
                connection.execute(text(f'CREATE ROLE {identifier(name)} NOLOGIN'))
            connection.execute(text(f'GRANT SELECT ON TABLE users TO {identifier(name)}'))
        connection.execute(text(f'GRANT USAGE, CREATE ON SCHEMA public TO {identifier(owner)}'))
        count = harden(connection, runtime, owner)
        assert count >= 41
        assert connection.scalar(text("SELECT has_schema_privilege(:role, 'public', 'CREATE')"), {'role': runtime}) is False
        assert connection.scalar(text("SELECT has_table_privilege(:role, 'users', 'SELECT')"), {'role': runtime}) is True
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text(f'SET LOCAL ROLE {identifier(runtime)}'))
                connection.execute(text('CREATE TABLE public.s25_denied (id text)'))
        for name in ('anon', 'authenticated'):
            if connection.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:name'), {'name': name}):
                assert connection.scalar(text("SELECT has_table_privilege(:role, 'users', 'SELECT')"), {'role': name}) is False
        connection.execute(text(f'SET LOCAL ROLE {identifier(owner)}'))
        connection.execute(text('CREATE TABLE public.s25_future (id text)'))
        connection.execute(text('RESET ROLE'))
        assert connection.scalar(text("SELECT has_table_privilege(:role, 's25_future', 'INSERT')"), {'role': runtime}) is True
        transaction.rollback()


def test_runtime_schema_owner_is_rejected(db):
    suffix = uuid4().hex[:12]
    runtime, owner = 's25_app_' + suffix, 's25_owner_' + suffix
    with engine().connect() as connection, connection.begin() as transaction:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
        for name in (runtime, owner):
            connection.execute(text(f'CREATE ROLE {identifier(name)} NOLOGIN'))
        connection.execute(text(f'ALTER SCHEMA public OWNER TO {identifier(runtime)}'))
        with pytest.raises(ValueError, match='application schema'):
            harden(connection, runtime, owner)
        transaction.rollback()


def test_runtime_inherited_roles_and_unreviewed_objects_fail_closed(db):
    suffix = uuid4().hex[:12]
    runtime, owner, inherited = ['s25_' + x + '_' + suffix for x in ('app', 'owner', 'inherited')]
    with engine().connect() as connection, connection.begin() as transaction:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
        for name in (runtime, owner, inherited):
            connection.execute(text(f'CREATE ROLE {identifier(name)} NOLOGIN'))
        connection.execute(text(f'GRANT {identifier(inherited)} TO {identifier(runtime)}'))
        with pytest.raises(ValueError, match='inherited role'):
            harden(connection, runtime, owner)
        connection.execute(text(f'REVOKE {identifier(inherited)} FROM {identifier(runtime)}'))
        connection.execute(text('CREATE TABLE public.s25_unreviewed (id text)'))
        with pytest.raises(ValueError, match='Unreviewed public'):
            harden(connection, runtime, owner)
        transaction.rollback()


def test_replication_roles_cannot_be_used_for_application_access(db):
    suffix = uuid4().hex[:12]
    runtime, owner = 's25_app_' + suffix, 's25_owner_' + suffix
    with engine().connect() as connection, connection.begin() as transaction:
        assert connection.scalar(text('SELECT current_database()')) == 'intraspot_mvp_test'
        connection.execute(text(f'CREATE ROLE {identifier(runtime)} NOLOGIN REPLICATION'))
        connection.execute(text(f'CREATE ROLE {identifier(owner)} NOLOGIN'))
        with pytest.raises(ValueError, match='non-administrative roles'):
            harden(connection, runtime, owner)
        transaction.rollback()


@pytest.mark.parametrize('name', ['x;DROP ROLE x', 'postgres"', 'a.b', 'UPPER', ''])
def test_role_identifiers_are_not_sql(name):
    with pytest.raises(ValueError):
        identifier(name)

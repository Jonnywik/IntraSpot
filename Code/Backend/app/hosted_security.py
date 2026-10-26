"""Explicit application-role hardening; never changes provider-managed objects."""
import argparse
import re

from sqlalchemy import inspect, text


def identifier(value: str) -> str:
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,62}', value):
        raise ValueError('Invalid application role identifier')
    return '"' + value + '"'


def harden(connection, runtime_role: str, migration_role: str) -> int:
    from app.api.router import api_router
    from app.db.session import Base
    api_router()  # Register the application metadata without running migrations.
    runtime, owner = identifier(runtime_role), identifier(migration_role)
    if runtime_role == migration_role or runtime_role in {'postgres', 'anon', 'authenticated', 'service_role'}:
        raise ValueError('Use separate dedicated application and migration roles')
    for name in (runtime_role, migration_role):
        role = connection.execute(text('SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication FROM pg_roles WHERE rolname=:name'), {'name': name}).one_or_none()
        if role is None or any(role):
            raise ValueError('Dedicated non-administrative roles must exist first')
    if connection.scalar(text('SELECT pg_has_role(:runtime, :owner, \'MEMBER\')'), {'runtime': runtime_role, 'owner': migration_role}):
        raise ValueError('Runtime must not inherit the migration role')
    if connection.scalar(text('SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=:role)'), {'role': runtime_role}):
        raise ValueError('Runtime must have no inherited role memberships')
    if connection.scalar(text("SELECT pg_has_role(:role, pg_get_userbyid(nspowner), 'MEMBER') FROM pg_namespace WHERE nspname='public'"), {'role': runtime_role}):
        raise ValueError('Runtime must not own the application schema')
    tables = sorted(set(inspect(connection).get_table_names(schema='public')) & set(Base.metadata.tables))
    unknown = set(inspect(connection).get_table_names(schema='public')) - set(Base.metadata.tables) - {'alembic_version'}
    if unknown or inspect(connection).get_view_names(schema='public') or connection.scalar(text(
        "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='public' AND NOT EXISTS (SELECT 1 FROM pg_depend d "
        "WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')"
    )):
        raise ValueError('Unreviewed public objects require a scoped permission review')
    if connection.scalar(text(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND pg_has_role(:role, pg_get_userbyid(c.relowner), 'MEMBER')"
    ), {'role': runtime_role}):
        raise ValueError('Runtime must not own application objects')
    connection.execute(text('REVOKE CREATE ON SCHEMA public FROM PUBLIC'))
    connection.execute(text(f'REVOKE CREATE ON SCHEMA public FROM {runtime}'))
    connection.execute(text(f'GRANT USAGE ON SCHEMA public TO {runtime}'))
    connection.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC'))
    connection.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {runtime}'))
    for browser in ('anon', 'authenticated'):
        if connection.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:name'), {'name': browser}):
            connection.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public REVOKE ALL ON TABLES FROM {identifier(browser)}'))
            connection.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {identifier(browser)}'))
            connection.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM {identifier(browser)}'))
    connection.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC'))
    for name in tables:
        table = 'public.' + identifier(name)
        connection.execute(text(f'REVOKE ALL ON TABLE {table} FROM PUBLIC'))
        for browser in ('anon', 'authenticated'):
            if connection.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:name'), {'name': browser}):
                connection.execute(text(f'REVOKE ALL ON TABLE {table} FROM {identifier(browser)}'))
        connection.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}'))
    return len(tables)


def main():
    from sqlalchemy import create_engine
    from app.core.config import get_settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-role', required=True)
    parser.add_argument('--migration-role', required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.environment != 'hosted' or not settings.migration_database_url:
        raise SystemExit('Explicit hosted migration configuration required')
    with create_engine(settings.migration_database_url).begin() as connection:
        count = harden(connection, args.runtime_role, args.migration_role)
    print(f'Application grants hardened for {count} tables. Verify Data API is disabled separately.')


if __name__ == '__main__':
    main()

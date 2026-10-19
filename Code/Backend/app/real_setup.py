"""Explicit isolated Auth setup; never overwrite the fictional configuration."""
import argparse
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import ROOT, Settings


def write_new_or_matching(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding='utf-8') != content:
            raise RuntimeError('Existing real-development configuration differs; nothing was overwritten.')
        return
    with path.open('x', encoding='utf-8', newline='\n') as destination:
        destination.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description='Configure isolated development using PUBLIC Supabase settings only.')
    parser.add_argument('--supabase-url', required=True)
    parser.add_argument('--publishable-key', required=True)
    arguments = parser.parse_args()
    base = Settings()
    source = make_url(base.database_url)
    if base.auth_provider != 'fixture' or not base.fixture_auth or base.environment != 'local' or source.database != 'intraspot_mvp':
        raise RuntimeError('Run isolated setup from the existing local fictional configuration.')
    target = source.set(database='intraspot_real_dev')
    configured = Settings(_env_file=None, environment='local', auth_provider='supabase', fixture_auth=False,
        database_url=target.render_as_string(hide_password=False),
        supabase_url=arguments.supabase_url, supabase_publishable_key=arguments.publishable_key,
        cors_origins=['http://localhost:3001', 'http://127.0.0.1:3001'])
    backend_content = '\n'.join([
        'ENVIRONMENT=local', 'AUTH_PROVIDER=supabase', 'FIXTURE_AUTH=false',
        'DATABASE_URL=' + configured.database_url,
        'SUPABASE_URL=' + configured.supabase_url,
        'SUPABASE_PUBLISHABLE_KEY=' + configured.supabase_publishable_key,
        'CORS_ORIGINS=["http://localhost:3001","http://127.0.0.1:3001"]', '',
    ])
    frontend_content = '\n'.join([
        'NEXT_PUBLIC_AUTH_MODE=supabase', 'NEXT_PUBLIC_LOCAL_DEMO=false',
        'NEXT_PUBLIC_API_URL=http://127.0.0.1:8011',
        'NEXT_PUBLIC_SUPABASE_URL=' + configured.supabase_url,
        'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=' + configured.supabase_publishable_key, '',
    ])
    files = [(ROOT / '.env.real.local', backend_content),
             (ROOT.parent / 'Frontend/.env.real.local', frontend_content)]
    # Check both before creating anything; conflicting user configuration is preserved.
    if any(path.exists() and path.read_text(encoding='utf-8') != content for path, content in files):
        raise RuntimeError('Existing real-development configuration differs; nothing was overwritten.')
    administrator = create_engine(base.database_url, isolation_level='AUTOCOMMIT')
    try:
        with administrator.connect() as connection:
            if connection.scalar(text('SELECT current_database()')) != 'intraspot_mvp':
                raise RuntimeError('Unexpected setup source database.')
            if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname='intraspot_real_dev'")):
                connection.execute(text('CREATE DATABASE intraspot_real_dev'))
    finally:
        administrator.dispose()
    for path, content in files:
        write_new_or_matching(path, content)
    print('Separate local real-development database and ignored configurations are ready. No migration or fixture seeding ran.')
    print('Explicitly apply the reviewed migrations with INTRASPOT_CONFIG=real before starting API 8011.')


if __name__ == '__main__':
    main()

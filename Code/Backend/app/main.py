import json
import logging
from uuid import uuid4
from alembic.config import Config
from alembic.script import ScriptDirectory

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException

from app.api.router import api_router
from app.core.config import ROOT, get_settings
from app.core.errors import DomainError, domain_error, error_response, http_error, validation_error
from app.db.session import engine

log = logging.getLogger('intraspot.actions')


def create_app():
    settings = get_settings()
    expected_migration = ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
    instance_id = str(uuid4())
    description = ('Isolated real-auth development only. Not approved for production.'
                   if settings.auth_provider == 'supabase' else
                   'Fictional local demonstration only. Not approved for production.')
    app = FastAPI(title='IntraSpot local MVP', version='0.1.0', description=description)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                       allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key', 'If-Match'],
                       expose_headers=['X-Request-ID'])
    app.add_exception_handler(DomainError, domain_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)

    @app.middleware('http')
    async def metadata_only(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(request, 500, 'internal_error', 'Request failed. Please retry.')
        route = request.scope.get('route')
        log.info(json.dumps({'request_id': request.state.request_id,
                             'action': getattr(route, 'path', 'unmatched'),
                             'status': response.status_code}))
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    @app.get('/health')
    def health():
        return {'status': 'ok', 'environment': settings.environment, 'instance_id': instance_id}

    @app.get('/ready')
    def ready():
        try:
            with engine().connect() as connection:
                version = connection.scalar(text('SELECT version_num FROM alembic_version'))
            if version != expected_migration:
                raise RuntimeError('migration required')
        except Exception:
            raise DomainError('database_not_ready', 'Apply the reviewed local migration first.', 503)
        return {'status': 'ready', 'migration': version}

    app.include_router(api_router())
    return app


app = create_app()

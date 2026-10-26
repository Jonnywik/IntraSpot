import json
import logging
import asyncio
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
from app.maintenance import lifespan

log = logging.getLogger('intraspot.actions')


def create_app():
    settings = get_settings()
    expected_migration = ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
    description = ('Isolated real-auth development only. Not approved for production.'
                   if settings.auth_provider == 'supabase' else
                   'Fictional local demonstration only. Not approved for production.')
    app = FastAPI(title='IntraSpot local MVP', version='0.1.0', description=description, lifespan=lifespan)
    @app.middleware('http')
    async def ip_admission(request: Request, call_next):
        from app.rate_limits import check_ip
        try:
            await asyncio.to_thread(check_ip, request)
        except DomainError as exc:
            return await domain_error(request, exc)
        return await call_next(request)

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
                       allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key', 'If-Match'],
                       expose_headers=['X-Request-ID', 'Retry-After'])
    app.add_exception_handler(DomainError, domain_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)

    @app.middleware('http')
    async def metadata_only(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception as exc:
            # Categories only: exception strings can contain SQL parameters or tokens.
            log.error(json.dumps({'request_id': request.state.request_id,
                                  'error_code': type(exc).__name__}))
            response = error_response(request, 500, 'internal_error', 'Request failed. Please retry.')
        route = request.scope.get('route')
        log.info(json.dumps({'request_id': request.state.request_id,
                             'action': getattr(route, 'path', 'unmatched'),
                             'status': response.status_code}))
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/ready')
    def ready():
        try:
            with engine().connect() as connection:
                version = connection.scalar(text('SELECT version_num FROM alembic_version'))
            if version != expected_migration:
                raise RuntimeError('migration required')
        except Exception:
            raise DomainError('database_not_ready', 'The service is starting. Please retry shortly.', 503)
        return {'status': 'ready'}

    app.include_router(api_router())
    return app


app = create_app()

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
    request_id: str | None


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status


def error_response(request: Request, status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={
        'error': {'code': code, 'message': message},
        'request_id': getattr(request.state, 'request_id', None),
    })


async def domain_error(request: Request, exc: DomainError):
    return error_response(request, exc.status, exc.code, exc.message)


async def validation_error(request: Request, exc: RequestValidationError):
    return error_response(request, 422, 'validation_error', 'Check the required fields and their formats.')


async def http_error(request: Request, exc: HTTPException):
    return error_response(request, exc.status_code, 'http_error', 'Request could not be completed.')

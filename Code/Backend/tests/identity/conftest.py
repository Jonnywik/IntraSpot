import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import current_actor, optional_actor, require_eligible
from app.core.contracts import Actor
from app.core.errors import DomainError, domain_error
from app.db.session import get_db


@pytest.fixture
def auth_dependency_client(db):
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error)

    def test_db():
        yield db

    app.dependency_overrides[get_db] = test_db

    @app.get("/optional")
    def optional_route(actor: Actor | None = Depends(optional_actor)):
        return {"id": actor.user_id if actor else None}

    @app.get("/required")
    def required_route(actor: Actor = Depends(current_actor)):
        return {"id": actor.user_id}

    @app.get("/eligible")
    def eligible_route(actor: Actor = Depends(require_eligible)):
        return {"id": actor.user_id}

    with TestClient(app) as client:
        yield client

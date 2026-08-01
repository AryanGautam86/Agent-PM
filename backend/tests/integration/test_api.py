"""API-level tests.

These run without a database: they cover the surface that must behave
correctly before any query happens — liveness, authentication, the error
envelope, and the shape of the OpenAPI contract the frontend is written
against.

Tests that need real persistence are marked ``integration`` and skipped unless
``DATABASE_URL`` is set.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from agent_pm.api.deps import get_db
from agent_pm.core.config import Settings
from agent_pm.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(environment="local", database_url="", debug=True))
    # No lifespan: it would build a database engine we do not need here.
    return TestClient(app)


def test_liveness_does_not_touch_the_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_points_at_the_health_check(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["service"] == "agent-pm"


def test_protected_routes_require_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/engagements")

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "unauthenticated"
    assert "Missing Authorization header" in body["message"]
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_malformed_authorization_header_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/engagements", headers={"Authorization": "Token abc123"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_garbage_token_is_rejected_not_accepted(client: TestClient) -> None:
    """A token that is not verifiable must never authenticate anybody."""
    response = client.get(
        "/api/v1/engagements", headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert response.status_code == 401


def test_every_error_uses_the_same_envelope(client: TestClient) -> None:
    body = client.get("/api/v1/engagements").json()

    assert set(body) == {"code", "message", "details"}


def test_request_id_is_echoed_for_support(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"


def test_unknown_path_is_a_404(client: TestClient) -> None:
    assert client.get("/api/v1/nope").status_code == 404


def test_meeting_webhook_validates_its_envelope() -> None:
    """The one unauthenticated route still refuses a malformed body.

    ``get_db`` is overridden because FastAPI resolves dependencies alongside
    body validation, so without a database the request would fail on the
    session rather than on the envelope — which is not what this asserts.
    """
    app = create_app(Settings(environment="local", database_url=""))
    app.dependency_overrides[get_db] = lambda: None

    with TestClient(app) as stubbed:
        response = stubbed.post(
            "/api/v1/events/meeting-outcome", json={"nonsense": True}
        )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    # The consent and engagement fields are what the contract turns on.
    missing = {
        tuple(error["loc"])[-1] for error in response.json()["details"]["errors"]
    }
    assert {"engagement_slug", "external_id", "consented"} <= missing


def test_openapi_documents_the_contract_the_frontend_uses(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    for expected in (
        "/api/v1/health/ready",
        "/api/v1/auth/me",
        "/api/v1/engagements",
        "/api/v1/engagements/{engagement_id}/standups/morning",
        "/api/v1/engagements/{engagement_id}/standups/eod",
        "/api/v1/engagements/{engagement_id}/raid/gap-scan",
        "/api/v1/engagements/{engagement_id}/approvals/{approval_id}/decision",
        "/api/v1/engagements/{engagement_id}/reports/weekly-status",
        "/api/v1/events/meeting-outcome",
        "/api/v1/agent/tasks",
    ):
        assert expected in paths, f"{expected} is missing from the API"


def test_docs_are_hidden_in_production() -> None:
    app = create_app(Settings(environment="prod", database_url=""))
    with TestClient(app) as production:
        assert production.get("/docs").status_code == 404


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs a live database"
)
def test_readiness_reports_the_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["database"] == "ok"

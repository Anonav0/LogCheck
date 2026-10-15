"""Tests for FastAPI health and readiness endpoints."""

from __future__ import annotations

from app.core.config import Settings
from app.main import create_app
from tests.asgi_client import ASGIClient


def test_health_liveness_endpoint(api_client: ASGIClient) -> None:
    """Test that GET /health returns 200 and documented liveness schema."""
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "LogLens AI"

    # Correlation headers
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0
    assert "x-process-time" in response.headers


def test_health_ready_with_llm_disabled(clean_settings: Settings) -> None:
    """Test that GET /health/ready reports ready with llm_available=False when LLM disabled."""
    clean_settings.LLM_ENABLED = False
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ready"
    assert data["llm_enabled"] is False
    assert data["llm_available"] is False
    assert "x-request-id" in response.headers


def test_health_ready_with_mock_provider(clean_settings: Settings) -> None:
    """Test that GET /health/ready reports llm_available=True with mock provider."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "mock"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ready"
    assert data["llm_enabled"] is True
    assert data["llm_available"] is True


def test_health_ready_with_openai_no_key(clean_settings: Settings) -> None:
    """Test that GET /health/ready reports llm_available=False if OpenAI provider has no key."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "openai"
    clean_settings.LLM_API_KEY = ""
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ready"
    assert data["llm_enabled"] is True
    assert data["llm_available"] is False


def test_health_ready_with_openai_with_key(clean_settings: Settings) -> None:
    """Test that GET /health/ready reports llm_available=True when OpenAI key is set (strictly offline)."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "openai"
    clean_settings.LLM_API_KEY = "sk-test-dummy-key"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ready"
    assert data["llm_enabled"] is True
    assert data["llm_available"] is True

    # Verify no secret leak
    assert "sk-test-dummy-key" not in response.text


def test_request_id_propagation_and_fallback(api_client: ASGIClient) -> None:
    """Test custom X-Request-ID propagation and fallback for invalid formats."""
    # Valid custom request ID
    custom_id = "req-custom-trace-12345"
    res1 = api_client.get("/health", headers={"X-Request-ID": custom_id})
    assert res1.status_code == 200
    assert res1.headers["x-request-id"] == custom_id

    # Malformed/untrusted request ID (e.g. contains spaces, invalid characters, or too long)
    invalid_id = "bad id with spaces and <script>"
    res2 = api_client.get("/health", headers={"X-Request-ID": invalid_id})
    assert res2.status_code == 200
    assert res2.headers["x-request-id"] != invalid_id
    assert len(res2.headers["x-request-id"]) > 0

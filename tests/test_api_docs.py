"""Tests for OpenAPI specification and interactive documentation endpoints."""

from __future__ import annotations

from tests.asgi_client import ASGIClient


def test_openapi_json_specification(api_client: ASGIClient) -> None:
    """Test that /openapi.json is accessible and valid."""
    response = api_client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "LogLens AI API"
    assert spec["info"]["version"] == "1.0.0"

    # Verify registered paths
    paths = spec["paths"]
    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/api/v1/analyze" in paths

    # Verify methods
    assert "get" in paths["/health"]
    assert "get" in paths["/health/ready"]
    assert "post" in paths["/api/v1/analyze"]

    # Verify component schemas
    schemas = spec["components"]["schemas"]
    assert "AnalyzeLogRequest" in schemas
    assert "AnalyzeLogResponse" in schemas
    assert "ErrorResponse" in schemas
    assert "HealthResponse" in schemas
    assert "ReadyResponse" in schemas


def test_swagger_docs_accessible(api_client: ASGIClient) -> None:
    """Test that /docs Swagger UI endpoint is accessible."""
    response = api_client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower() or "html" in response.text.lower()


def test_redoc_accessible(api_client: ASGIClient) -> None:
    """Test that /redoc endpoint is accessible."""
    response = api_client.get("/redoc")
    assert response.status_code == 200
    assert "redoc" in response.text.lower() or "html" in response.text.lower()

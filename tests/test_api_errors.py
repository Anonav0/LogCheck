"""Tests for FastAPI input validation, error handling, and status codes."""

from __future__ import annotations

from app.core.config import Settings
from app.main import create_app
from tests.asgi_client import ASGIClient


def test_missing_log_text(api_client: ASGIClient) -> None:
    """Test that missing log_text returns HTTP 422 with standardized ErrorResponse."""
    response = api_client.post("/api/v1/analyze", json={"include_ai": False})
    assert response.status_code == 422
    data = response.json()

    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "log_text" in data["error"]["message"].lower()
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"] == data["error"]["request_id"]


def test_empty_or_whitespace_log_text(api_client: ASGIClient) -> None:
    """Test that empty or whitespace-only log returns HTTP 422."""
    for empty_val in ["", "   ", "\n\t  \n"]:
        response = api_client.post("/api/v1/analyze", json={"log_text": empty_val})
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] in ("EMPTY_LOG_INPUT", "VALIDATION_ERROR")


def test_malformed_json_returns_400(api_client: ASGIClient) -> None:
    """Test that non-JSON or malformed JSON payloads return HTTP 400."""
    response = api_client.post(
        "/api/v1/analyze",
        data="{malformed: json, missing quotes",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    data = response.json()

    assert data["error"]["code"] == "MALFORMED_JSON"
    assert "JSON" in data["error"]["message"]


def test_wrong_field_types(api_client: ASGIClient) -> None:
    """Test that wrong field types return HTTP 422."""
    # include_ai should be a boolean, log_text should be a string
    response = api_client.post(
        "/api/v1/analyze",
        json={"log_text": 12345, "include_ai": "not_a_boolean"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_extra_forbidden_fields_returns_422(api_client: ASGIClient) -> None:
    """Test that extra unrecognised fields return HTTP 422 due to extra='forbid'."""
    response = api_client.post(
        "/api/v1/analyze",
        json={
            "log_text": "2026-10-14 10:00:00 INFO all good",
            "unknown_extra_field": "disallowed",
        },
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "extra" in data["error"]["message"].lower()


def test_oversized_log_bytes_returns_413(clean_settings: Settings) -> None:
    """Test that exceeding MAX_LOG_SIZE_BYTES returns HTTP 413."""
    clean_settings.MAX_LOG_SIZE_BYTES = 50  # tiny limit
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    oversized_text = "A" * 100
    response = client.post("/api/v1/analyze", json={"log_text": oversized_text})
    assert response.status_code == 413
    data = response.json()
    assert data["error"]["code"] == "LOG_TOO_LARGE"


def test_too_many_lines_returns_413(clean_settings: Settings) -> None:
    """Test that exceeding MAX_LOG_LINES returns HTTP 413."""
    clean_settings.MAX_LOG_LINES = 5  # tiny limit
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    multi_line_text = "line\n" * 10
    response = client.post("/api/v1/analyze", json={"log_text": multi_line_text})
    assert response.status_code == 413
    data = response.json()
    assert data["error"]["code"] == "TOO_MANY_LOG_LINES"


def test_excessively_long_line_returns_413(clean_settings: Settings) -> None:
    """Test that exceeding MAX_LOG_LINE_LENGTH returns HTTP 413."""
    clean_settings.MAX_LOG_LINE_LENGTH = 20  # tiny limit
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    long_line = "2026-10-14 10:00:00 " + ("X" * 30)
    response = client.post("/api/v1/analyze", json={"log_text": long_line})
    assert response.status_code == 413
    data = response.json()
    assert data["error"]["code"] == "LOG_LINE_TOO_LONG"


def test_unicode_and_newlines_handled_gracefully(api_client: ASGIClient) -> None:
    """Test that Unicode characters (emojis, accents) and trailing newlines are safely parsed."""
    unicode_log = (
        "2026-10-14 10:00:00 ERROR auth.module - 🚨 用户认证失败: café inválido\n\n\n"
    )
    response = api_client.post("/api/v1/analyze", json={"log_text": unicode_log})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("completed", "completed_with_warnings")
    assert data["metrics"]["total_failure_events"] >= 1

"""Tests for the Streamlit HTTP API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from frontend.api_client import (
    DEFAULT_API_URL,
    analyze_logs,
    check_health,
    check_readiness,
    get_api_base_url,
)


def test_get_api_base_url_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test default API base URL when env var is not set."""
    monkeypatch.delenv("LOGLENS_API_URL", raising=False)
    assert get_api_base_url() == DEFAULT_API_URL


def test_get_api_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test custom API base URL from env var."""
    monkeypatch.setenv("LOGLENS_API_URL", "http://my-backend:9000/")
    assert get_api_base_url() == "http://my-backend:9000"


def test_check_health_success() -> None:
    """Test successful health check call."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "service": "LogLens AI"}

    with patch("requests.get", return_value=mock_resp) as mock_get:
        data, err = check_health("http://127.0.0.1:8000")
        assert err is None
        assert data == {"status": "ok", "service": "LogLens AI"}
        mock_get.assert_called_once_with("http://127.0.0.1:8000/health", timeout=5.0)


def test_check_health_connection_error() -> None:
    """Test connection error handling for health check."""
    with patch(
        "requests.get",
        side_effect=requests.exceptions.ConnectionError("Connection refused"),
    ):
        data, err = check_health("http://127.0.0.1:8000")
        assert data is None
        assert err is not None
        assert "Could not connect" in err
        assert "ensure the backend is running" in err.lower()


def test_check_health_timeout() -> None:
    """Test timeout handling for health check."""
    with patch(
        "requests.get",
        side_effect=requests.exceptions.Timeout("Read timed out"),
    ):
        data, err = check_health("http://127.0.0.1:8000")
        assert data is None
        assert err is not None
        assert "timed out" in err.lower()


def test_check_readiness_success() -> None:
    """Test successful readiness check call."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ready",
        "llm_enabled": True,
        "llm_available": True,
    }

    with patch("requests.get", return_value=mock_resp):
        data, err = check_readiness("http://127.0.0.1:8000")
        assert err is None
        assert data["llm_available"] is True


def test_analyze_logs_success() -> None:
    """Test successful log analysis call."""
    expected_response = {
        "request_id": "test-req-123",
        "status": "completed",
        "metrics": {"total_log_lines": 10, "total_failure_events": 1},
        "failure_groups": [],
        "failure_events": [],
        "parser_warnings": [],
        "ai_analysis": None,
        "analysis_source": "none",
        "processing_time_ms": 12.34,
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = expected_response

    with patch("requests.post", return_value=mock_resp) as mock_post:
        data, err = analyze_logs("2026-10-14 10:00:00 ERROR fail", include_ai=False)
        assert err is None
        assert data == expected_response
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["include_ai"] is False
        assert "log_text" in call_kwargs["json"]


def test_analyze_logs_connection_error() -> None:
    """Test connection failure when backend is down during analysis."""
    with patch(
        "requests.post",
        side_effect=requests.exceptions.ConnectionError("Connection refused"),
    ):
        data, err = analyze_logs("sample log")
        assert data is None
        assert err is not None
        assert "Cannot connect to LogLens AI API" in err
        assert "uvicorn app.main:app" in err


def test_analyze_logs_timeout() -> None:
    """Test analysis timeout handling."""
    with patch(
        "requests.post",
        side_effect=requests.exceptions.Timeout("Request timed out"),
    ):
        data, err = analyze_logs("sample log", timeout=10.0)
        assert data is None
        assert err is not None
        assert "timed out after 10 seconds" in err


def test_analyze_logs_413_payload_too_large() -> None:
    """Test HTTP 413 error payload parsing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 413
    mock_resp.json.return_value = {
        "error": {
            "code": "LOG_TOO_LARGE",
            "message": "Log input size exceeds maximum allowed bytes.",
            "limit": 1048576,
            "actual": 2000000,
        }
    }

    with patch("requests.post", return_value=mock_resp):
        data, err = analyze_logs("oversized log")
        assert data is None
        assert err is not None
        assert "LOG_TOO_LARGE" in err
        assert "Limit: 1,048,576" in err
        assert "Actual: 2,000,000" in err


def test_analyze_logs_422_validation_error() -> None:
    """Test HTTP 422 error payload parsing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.json.return_value = {
        "error": {
            "code": "EMPTY_LOG_INPUT",
            "message": "The submitted log input is empty or contains only whitespace.",
        }
    }

    with patch("requests.post", return_value=mock_resp):
        data, err = analyze_logs("   ")
        assert data is None
        assert err is not None
        assert "EMPTY_LOG_INPUT" in err


def test_analyze_logs_500_server_error() -> None:
    """Test HTTP 500 error payload parsing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.json.return_value = {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected internal server error occurred.",
        }
    }

    with patch("requests.post", return_value=mock_resp):
        data, err = analyze_logs("some log")
        assert data is None
        assert err is not None
        assert "INTERNAL_SERVER_ERROR" in err


def test_analyze_logs_malformed_json_response() -> None:
    """Test handling of 200 response with invalid JSON body."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Invalid JSON")

    with patch("requests.post", return_value=mock_resp):
        data, err = analyze_logs("some log")
        assert data is None
        assert err is not None
        assert "not valid JSON" in err

"""Tests for FastAPI log analysis endpoint (POST /api/v1/analyze)."""

from __future__ import annotations

from unittest.mock import patch

from app.core.config import Settings
from app.main import create_app
from app.services.llm import (
    LLMRateLimitError,
    LLMTimeoutError,
)
from tests.asgi_client import ASGIClient


def test_analyze_clean_log(api_client: ASGIClient) -> None:
    """Test analysis on a clean log with no error lines."""
    clean_log = (
        "2026-10-14 10:00:00 INFO app.server - Server started\n"
        "2026-10-14 10:00:01 INFO app.server - Health check OK\n"
        "2026-10-14 10:00:02 INFO app.server - Request processed successfully\n"
    )

    response = api_client.post(
        "/api/v1/analyze",
        json={"log_text": clean_log, "include_ai": False},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "completed"
    assert data["metrics"]["total_log_lines"] == 3
    assert data["metrics"]["total_failure_events"] == 0
    assert data["metrics"]["unique_failure_groups"] == 0
    assert len(data["failure_events"]) == 0
    assert len(data["failure_groups"]) == 0
    assert data["ai_analysis"] is None
    assert data["analysis_source"] == "none"
    assert data["processing_time_ms"] >= 0
    assert "request_id" in data
    assert response.headers["x-request-id"] == data["request_id"]
    assert "x-process-time" in response.headers


def test_analyze_sample_application_log(
    api_client: ASGIClient, sample_application_log_text: str
) -> None:
    """Test deterministic analysis on sample_application.log fixture."""
    response = api_client.post(
        "/api/v1/analyze",
        json={"log_text": sample_application_log_text, "include_ai": False},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ("completed", "completed_with_warnings")
    metrics = data["metrics"]
    assert metrics["total_log_lines"] > 0
    assert metrics["total_failure_events"] > 0
    assert metrics["unique_failure_groups"] > 0

    # Ensure events and groups match metrics
    assert len(data["failure_events"]) == metrics["total_failure_events"]
    assert len(data["failure_groups"]) == metrics["unique_failure_groups"]

    # Verify line references are accurate and within range
    for event in data["failure_events"]:
        assert (
            1
            <= event["start_line_number"]
            <= event["end_line_number"]
            <= metrics["total_log_lines"]
        )
        assert 1 <= event["primary_line_number"] <= metrics["total_log_lines"]

    for group in data["failure_groups"]:
        assert len(group["fingerprint"]) == 64
        assert group["occurrence_count"] >= 1
        assert (
            1
            <= group["first_seen_line"]
            <= group["last_seen_line"]
            <= metrics["total_log_lines"]
        )

    assert data["ai_analysis"] is None
    assert data["analysis_source"] == "none"


def test_analyze_sample_test_failure_log(
    api_client: ASGIClient, sample_test_failure_log_text: str
) -> None:
    """Test deterministic analysis on sample_test_failure.log fixture."""
    response = api_client.post(
        "/api/v1/analyze",
        json={"log_text": sample_test_failure_log_text, "include_ai": False},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ("completed", "completed_with_warnings")
    assert data["metrics"]["total_failure_events"] >= 1
    assert len(data["failure_groups"]) >= 1


def test_analyze_recurring_failures_log(
    api_client: ASGIClient, recurring_failures_log_text: str
) -> None:
    """Test deterministic analysis and grouping on recurring_failures.log fixture."""
    response = api_client.post(
        "/api/v1/analyze",
        json={"log_text": recurring_failures_log_text, "include_ai": False},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ("completed", "completed_with_warnings")
    # Recurring failures should result in groups with occurrence_count > 1
    has_recurring = any(g["occurrence_count"] > 1 for g in data["failure_groups"])
    assert has_recurring is True
    assert data["metrics"]["repeated_failure_groups"] >= 1


def test_analyze_include_ai_false_skips_llm(
    clean_settings: Settings, sample_application_log_text: str
) -> None:
    """Test that include_ai=False prevents LLM invocation even if LLM is enabled."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "mock"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    with patch("app.api.routes.analysis.analyze_failures_with_ai") as mock_ai:
        response = client.post(
            "/api/v1/analyze",
            json={"log_text": sample_application_log_text, "include_ai": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ai_analysis"] is None
        assert data["analysis_source"] == "none"
        mock_ai.assert_not_called()


def test_analyze_include_ai_true_when_server_llm_disabled(
    clean_settings: Settings, sample_application_log_text: str
) -> None:
    """Test that include_ai=True returns deterministic fallback when server LLM is disabled."""
    clean_settings.LLM_ENABLED = False
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    with patch("app.api.routes.analysis.analyze_failures_with_ai") as mock_ai:
        response = client.post(
            "/api/v1/analyze",
            json={"log_text": sample_application_log_text, "include_ai": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed_with_fallback"
        assert data["analysis_source"] == "fallback"
        assert data["ai_analysis"] is not None
        mock_ai.assert_not_called()


def test_analyze_include_ai_true_with_mock_provider(
    clean_settings: Settings, sample_application_log_text: str
) -> None:
    """Test end-to-end analysis with include_ai=True and Mock LLM provider."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "mock"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    response = client.post(
        "/api/v1/analyze",
        json={"log_text": sample_application_log_text, "include_ai": True},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in (
        "completed",
        "completed_with_warnings",
        "completed_with_fallback",
    )
    ai_res = data["ai_analysis"]
    assert ai_res is not None
    assert len(ai_res["summary"]) > 0
    assert isinstance(ai_res["likely_causes"], list)
    assert isinstance(ai_res["recommended_actions"], list)
    assert 0.0 <= ai_res["confidence"] <= 1.0

    # Ensure evidence lines in AI response match valid source lines
    for cause in ai_res["likely_causes"]:
        for ev in cause["evidence_refs"]:
            assert 1 <= ev["line_number"] <= data["metrics"]["total_log_lines"]


def test_analyze_llm_timeout_fallback(
    clean_settings: Settings, sample_application_log_text: str
) -> None:
    """Test that LLM provider timeout safely falls back with completed_with_fallback."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "mock"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    with patch(
        "app.services.llm.provider_factory.MockLLMProvider.generate",
        side_effect=LLMTimeoutError("LLM call timed out after 10.0s"),
    ):
        response = client.post(
            "/api/v1/analyze",
            json={"log_text": sample_application_log_text, "include_ai": True},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "completed_with_fallback"
        assert data["analysis_source"] == "fallback"
        assert data["ai_analysis"] is not None
        # Deterministic output must remain intact
        assert data["metrics"]["total_failure_events"] > 0
        assert len(data["failure_groups"]) > 0


def test_analyze_llm_rate_limit_fallback(
    clean_settings: Settings, sample_application_log_text: str
) -> None:
    """Test that LLM rate limit triggers deterministic fallback."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "mock"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    with patch(
        "app.services.llm.provider_factory.MockLLMProvider.generate",
        side_effect=LLMRateLimitError("Provider rate limit reached (429)"),
    ):
        response = client.post(
            "/api/v1/analyze",
            json={"log_text": sample_application_log_text, "include_ai": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed_with_fallback"
        assert data["analysis_source"] == "fallback"


def test_analyze_llm_invalid_json_fallback(
    clean_settings: Settings, sample_application_log_text: str
) -> None:
    """Test that invalid non-JSON output from LLM triggers deterministic fallback."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "mock"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    with patch(
        "app.services.llm.provider_factory.MockLLMProvider.generate",
        return_value="Not valid json response from model",
    ):
        response = client.post(
            "/api/v1/analyze",
            json={"log_text": sample_application_log_text, "include_ai": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed_with_fallback"
        assert data["analysis_source"] == "fallback"


def test_analyze_llm_evidence_verification_error_fallback(
    clean_settings: Settings, sample_application_log_text: str
) -> None:
    """Test that fabricated evidence in LLM response triggers deterministic fallback."""
    clean_settings.LLM_ENABLED = True
    clean_settings.LLM_PROVIDER = "mock"
    app = create_app(settings=clean_settings)
    client = ASGIClient(app)

    with patch(
        "app.services.llm.analysis_service.verify_ai_evidence",
        return_value=(False, ["Hallucinated evidence line 9999"]),
    ):
        response = client.post(
            "/api/v1/analyze",
            json={"log_text": sample_application_log_text, "include_ai": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed_with_fallback"
        assert data["analysis_source"] == "fallback"


def test_analyze_unexpected_failure_returns_sanitized_500(
    api_client: ASGIClient,
) -> None:
    """Test that unexpected server error returns a sanitized 500 error response."""
    with patch(
        "app.api.routes.analysis.parse_log_text",
        side_effect=RuntimeError("internal crash: sensitive database leak"),
    ):
        response = api_client.post(
            "/api/v1/analyze",
            json={"log_text": "2026-10-14 10:00:00 ERROR failed", "include_ai": False},
        )
        assert response.status_code == 500
        data = response.json()

        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "sensitive database leak" not in response.text
        assert (
            "unexpected" in data["error"]["message"].lower()
            or "internal" in data["error"]["message"].lower()
        )
        assert "x-request-id" in response.headers

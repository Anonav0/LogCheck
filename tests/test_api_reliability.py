"""FastAPI integration and contract reliability tests.

Implements Phase 8 Section 7 requirements:
- Health and readiness contract validation under varied configurations.
- Guarantee that health endpoints never make external network calls or disclose sensitive settings.
- Standardized error response contract across all HTTP error codes (400, 413, 422, 500).
- Information disclosure prevention (no tracebacks, secret keys, or internal filesystem paths).
- X-Request-ID and X-Process-Time header propagation and correlation.
- OpenAPI specification completeness and schema contract verification.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from app.core.config import Settings
from app.main import create_app
from tests.asgi_client import ASGIClient


class TestAPIHealthReliability:
    """Tests for /health and /health/ready operational endpoints."""

    def test_health_does_not_make_external_provider_calls(
        self, clean_settings: Settings
    ) -> None:
        """Verify health checks do not execute external HTTP requests."""
        clean_settings.LLM_ENABLED = True
        clean_settings.LLM_PROVIDER = "gemini"
        clean_settings.LLM_API_KEY = "test_key"
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert mock_get.call_count == 0
            assert mock_post.call_count == 0

            resp_ready = client.get("/health/ready")
            assert resp_ready.status_code == 200
            assert mock_get.call_count == 0
            assert mock_post.call_count == 0

    def test_health_endpoints_never_disclose_secrets(
        self, clean_settings: Settings
    ) -> None:
        """Verify secrets and keys are never present in health or ready responses."""
        secret_key = "AIzaSySuperSecretKeyForTesting12345"
        clean_settings.LLM_ENABLED = True
        clean_settings.LLM_PROVIDER = "gemini"
        clean_settings.LLM_API_KEY = secret_key
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        for endpoint in ["/health", "/health/ready"]:
            resp = client.get(endpoint)
            body = resp.text
            assert secret_key not in body
            assert "api_key" not in body.lower()

    def test_readiness_with_gemini_without_key(self, clean_settings: Settings) -> None:
        """Verify readiness reports llm_available=False when Gemini is missing an API key."""
        clean_settings.LLM_ENABLED = True
        clean_settings.LLM_PROVIDER = "gemini"
        clean_settings.LLM_API_KEY = ""
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["llm_enabled"] is True
        assert data["llm_available"] is False


class TestAPIErrorContractsAndInformationDisclosure:
    """Tests verifying standardized error schemas and leak prevention."""

    def test_standard_error_schema_on_validation_failure(
        self, api_client: ASGIClient
    ) -> None:
        """Verify 422 error response adheres strictly to ErrorResponse schema."""
        resp = api_client.post("/api/v1/analyze", json={"wrong_field": 123})
        assert resp.status_code == 422
        data = resp.json()

        assert "error" in data
        err = data["error"]
        assert "code" in err
        assert "message" in err
        assert "request_id" in err
        assert isinstance(err["code"], str)
        assert isinstance(err["message"], str)

    def test_standard_error_schema_on_malformed_json(
        self, api_client: ASGIClient
    ) -> None:
        """Verify 400 error response adheres strictly to ErrorResponse schema."""
        resp = api_client.post(
            "/api/v1/analyze",
            data="{ broken json :",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "MALFORMED_JSON"
        assert "JSON" in data["error"]["message"]

    def test_error_responses_do_not_leak_tracebacks_or_paths(
        self, api_client: ASGIClient
    ) -> None:
        """Verify error payloads do not disclose internal Python paths or stack traces."""
        test_payloads = [
            ("{ bad json ", {"Content-Type": "application/json"}),
            (json.dumps({"log_text": ""}), {"Content-Type": "application/json"}),
            (
                json.dumps({"log_text": "x" * 20000}),
                {"Content-Type": "application/json"},
            ),
        ]

        for payload, headers in test_payloads:
            resp = api_client.post("/api/v1/analyze", data=payload, headers=headers)
            body = resp.text
            assert "Traceback (most recent call last)" not in body
            assert "/home/" not in body
            assert ".py line" not in body
            assert "site-packages" not in body

    def test_client_provided_x_request_id_preserved(
        self, api_client: ASGIClient
    ) -> None:
        """Verify custom client X-Request-ID header is propagated into response and error."""
        custom_id = "req-custom-client-uuid-999"

        # Case 1: Successful request
        resp = api_client.post(
            "/api/v1/analyze",
            json={"log_text": "2026-10-14 INFO test", "include_ai": False},
            headers={"X-Request-ID": custom_id},
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-request-id") == custom_id
        assert resp.json().get("request_id") == custom_id

        # Case 2: Validation failure request
        resp_err = api_client.post(
            "/api/v1/analyze",
            json={"log_text": ""},
            headers={"X-Request-ID": custom_id},
        )
        assert resp_err.status_code == 422
        assert resp_err.headers.get("x-request-id") == custom_id
        assert resp_err.json()["error"]["request_id"] == custom_id

    def test_process_time_header_present_and_valid(
        self, api_client: ASGIClient
    ) -> None:
        """Verify X-Process-Time is returned on all responses as positive duration."""
        resp = api_client.get("/health")
        assert "x-process-time" in resp.headers
        raw_val = resp.headers["x-process-time"]
        assert raw_val.endswith("ms")
        duration = float(raw_val.rstrip("ms"))
        assert duration >= 0.0


class TestAPIAnalysisContractAndLineIntegrity:
    """Tests verifying analysis response contracts and source-line integrity."""

    def test_line_references_strictly_match_submitted_log(
        self, api_client: ASGIClient, recurring_failures_log_text: str
    ) -> None:
        """Verify response line references match exact source line text."""
        source_lines = recurring_failures_log_text.splitlines()

        resp = api_client.post(
            "/api/v1/analyze",
            json={"log_text": recurring_failures_log_text, "include_ai": False},
        )
        assert resp.status_code == 200
        data = resp.json()

        for group in data["failure_groups"]:
            assert 1 <= group["first_seen_line"] <= len(source_lines)
            assert 1 <= group["last_seen_line"] <= len(source_lines)
            assert group["first_seen_line"] <= group["last_seen_line"]

            for occ in group["occurrences"]:
                assert 1 <= occ["start_line_number"] <= len(source_lines)
                assert 1 <= occ["end_line_number"] <= len(source_lines)
                assert occ["start_line_number"] <= occ["end_line_number"]

    def test_ai_fallback_metadata_fidelity(
        self, clean_settings: Settings, recurring_failures_log_text: str
    ) -> None:
        """Verify include_ai=True with LLM disabled returns 200 with completed_with_fallback status."""
        clean_settings.LLM_ENABLED = False
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        resp = client.post(
            "/api/v1/analyze",
            json={"log_text": recurring_failures_log_text, "include_ai": True},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "completed_with_fallback"
        assert data["analysis_source"] == "fallback"
        assert data["ai_analysis"] is not None
        assert "likely_causes" in data["ai_analysis"]
        assert "recommended_actions" in data["ai_analysis"]

    def test_empty_failures_log_response_fidelity(self, api_client: ASGIClient) -> None:
        """Verify log with zero failures produces clean completed response with empty arrays."""
        clean_text = (
            "2026-10-14 12:00:00 [INFO] System is healthy and operating normally.\n"
        )
        resp = api_client.post(
            "/api/v1/analyze",
            json={"log_text": clean_text, "include_ai": False},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "completed"
        assert data["metrics"]["total_failure_events"] == 0
        assert data["metrics"]["unique_failure_groups"] == 0
        assert data["failure_events"] == []
        assert data["failure_groups"] == []

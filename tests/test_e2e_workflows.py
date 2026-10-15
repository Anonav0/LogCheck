"""End-to-End Workflow Integration Tests.

Implements Phase 8 Section 9 representative workflows:
- Workflow A: Complete deterministic analysis pipeline from submission to frontend consumable payload.
- Workflow B: AI-assisted analysis pipeline with prompt bounding, mocked provider, evidence verification, and frontend display readiness.
- Workflow C: AI failure with automatic deterministic fallback, result provenance, and UI demarcation.
- Workflow D: Input validation rejection (oversized/malformed), ensuring parser and LLM are bypassed, returning safe errors.
- Workflow E: Source-reference integrity across failure groups, occurrences, and verified vs fabricated AI citations.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from app.core.config import Settings
from app.main import create_app
from app.services.llm.exceptions import LLMTimeoutError
from app.services.llm.provider_factory import MockLLMProvider
from frontend.utils import (
    build_source_html,
    split_source_lines,
    validate_line_references,
)
from tests.asgi_client import ASGIClient


class TestWorkflowADeterministicAnalysis:
    """Workflow A: Complete deterministic analysis without AI."""

    def test_workflow_a_deterministic_pipeline(
        self, clean_settings: Settings, recurring_failures_log_text: str
    ) -> None:
        """Submit a valid log -> Validate -> Parse -> Extract -> Group -> Return -> Frontend format."""
        clean_settings.LLM_ENABLED = False
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        # 1. Submit through FastAPI
        response = client.post(
            "/api/v1/analyze",
            json={"log_text": recurring_failures_log_text, "include_ai": False},
        )
        assert response.status_code == 200
        data = response.json()

        # 2. Verify deterministic parsing & grouping
        assert data["status"] == "completed"
        assert data["analysis_source"] == "none"
        assert data["ai_analysis"] is None
        assert data["metrics"]["total_log_lines"] > 0
        assert data["metrics"]["total_failure_events"] >= 4
        assert data["metrics"]["unique_failure_groups"] >= 2
        assert len(data["failure_groups"]) >= 2

        # 3. Verify ordering invariants
        groups = data["failure_groups"]
        counts = [g["occurrence_count"] for g in groups]
        assert counts == sorted(counts, reverse=True)

        # 4. Verify frontend can consume and render the response
        lines = split_source_lines(recurring_failures_log_text)
        top_group = groups[0]
        primary_lines = {top_group["first_seen_line"]}
        html = build_source_html(lines, highlight_primary=primary_lines)
        assert len(html) > 0
        assert top_group["representative_message"] in recurring_failures_log_text


class TestWorkflowBAIAssistedAnalysis:
    """Workflow B: AI-assisted analysis with verified evidence references."""

    def test_workflow_b_ai_assisted_pipeline(
        self, clean_settings: Settings, recurring_failures_log_text: str
    ) -> None:
        """Submit valid log with AI -> Deterministic analysis -> Mock provider -> Validate schema -> Verify evidence -> Return AI result."""
        clean_settings.LLM_ENABLED = True
        clean_settings.LLM_PROVIDER = "mock"

        # Mock AI response citing actual line 8 from recurring_failures.log
        ai_response_payload = json.dumps(
            {
                "summary": "Recurring database connectivity failures identified.",
                "likely_causes": [
                    {
                        "description": "Database cluster connection drop",
                        "reasoning": "DatabaseConnectionError thrown across multiple gateway workers.",
                        "evidence_refs": [
                            {
                                "line_number": 8,
                                "excerpt": "Connection lost to database cluster primary",
                            }
                        ],
                    }
                ],
                "recommended_actions": [
                    {
                        "action": "Check database server logs and connection limits.",
                        "rationale": "Connection drops suggest failover or pool exhaustion.",
                        "priority": "high",
                        "evidence_refs": [
                            {
                                "line_number": 8,
                                "excerpt": "Connection lost to database cluster primary",
                            }
                        ],
                    }
                ],
                "confidence": 0.95,
                "limitations": ["No infrastructure network telemetry provided."],
                "evidence_refs": [
                    {
                        "line_number": 8,
                        "excerpt": "Connection lost to database cluster primary",
                    }
                ],
            }
        )

        mock_provider = MockLLMProvider(response_text=ai_response_payload)

        with patch(
            "app.services.llm.analysis_service.get_llm_provider",
            return_value=mock_provider,
        ):
            app = create_app(settings=clean_settings)
            client = ASGIClient(app)

            response = client.post(
                "/api/v1/analyze",
                json={"log_text": recurring_failures_log_text, "include_ai": True},
            )
            assert response.status_code == 200
            data = response.json()

            # Verify AI analysis result
            assert data["status"] == "completed"
            assert data["analysis_source"] == "llm"
            assert data["ai_analysis"] is not None
            assert data["ai_analysis"]["confidence"] == 0.95
            assert len(data["ai_analysis"]["likely_causes"]) == 1

            # Verify frontend can highlight cited evidence line
            cited_lines = [
                ref["line_number"] for ref in data["ai_analysis"]["evidence_refs"]
            ]
            assert 8 in cited_lines
            valid_citations = validate_line_references(
                cited_lines, len(split_source_lines(recurring_failures_log_text))
            )
            assert 8 in valid_citations


class TestWorkflowCAIFailureWithFallback:
    """Workflow C: AI failure with automatic fallback to deterministic results."""

    def test_workflow_c_ai_provider_timeout_fallback(
        self, clean_settings: Settings, recurring_failures_log_text: str
    ) -> None:
        """Submit log with AI -> Provider times out -> Return completed_with_fallback with deterministic insights."""
        clean_settings.LLM_ENABLED = True
        clean_settings.LLM_PROVIDER = "mock"

        timeout_provider = MockLLMProvider(
            simulated_exception=LLMTimeoutError(
                "Request timed out", timeout_seconds=5.0
            )
        )

        with patch(
            "app.services.llm.analysis_service.get_llm_provider",
            return_value=timeout_provider,
        ):
            app = create_app(settings=clean_settings)
            client = ASGIClient(app)

            response = client.post(
                "/api/v1/analyze",
                json={"log_text": recurring_failures_log_text, "include_ai": True},
            )
            assert response.status_code == 200
            data = response.json()

            # Status must show completed_with_fallback
            assert data["status"] == "completed_with_fallback"
            assert data["analysis_source"] == "fallback"
            assert data["ai_analysis"] is not None
            # Fallback must still report valid deterministic causes
            assert len(data["ai_analysis"]["likely_causes"]) > 0
            assert len(data["failure_groups"]) >= 2


class TestWorkflowDInvalidInputRejection:
    """Workflow D: Input validation rejection before parser or LLM execution."""

    def test_workflow_d_oversized_log_rejection(self, clean_settings: Settings) -> None:
        """Submit oversized payload -> Reject with HTTP 413 -> Parser & LLM bypassed."""
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        # 1 MiB + 10 bytes payload
        line = "A" * 100 + "\n"
        oversized = line * 10486

        with (
            patch("app.api.routes.analysis.parse_log_text") as mock_parse,
            patch("app.api.routes.analysis.analyze_failures_with_ai") as mock_ai,
        ):
            response = client.post(
                "/api/v1/analyze",
                json={"log_text": oversized, "include_ai": True},
            )
            assert response.status_code == 413
            data = response.json()
            assert data["error"]["code"] == "LOG_TOO_LARGE"
            # Crucial requirement: parser and downstream AI service are never called
            assert mock_parse.call_count == 0
            assert mock_ai.call_count == 0

    def test_workflow_d_empty_log_rejection(self, clean_settings: Settings) -> None:
        """Submit whitespace-only payload -> Reject with HTTP 422 -> Parser bypassed."""
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        with patch("app.api.routes.analysis.parse_log_text") as mock_parse:
            response = client.post(
                "/api/v1/analyze",
                json={"log_text": "   \n\t  \n", "include_ai": False},
            )
            assert response.status_code == 422
            data = response.json()
            assert data["error"]["code"] in ("EMPTY_LOG_INPUT", "VALIDATION_ERROR")
            assert mock_parse.call_count == 0


class TestWorkflowESourceReferenceIntegrity:
    """Workflow E: End-to-end source reference and evidence verification integrity."""

    def test_workflow_e_source_reference_navigation(
        self, clean_settings: Settings, recurring_failures_log_text: str
    ) -> None:
        """Analyze multi-failure log -> Select group/occurrence -> Verify source lines -> Reject hallucinated citation."""
        clean_settings.LLM_ENABLED = False
        app = create_app(settings=clean_settings)
        client = ASGIClient(app)

        response = client.post(
            "/api/v1/analyze",
            json={"log_text": recurring_failures_log_text, "include_ai": False},
        )
        assert response.status_code == 200
        data = response.json()

        source_lines = split_source_lines(recurring_failures_log_text)
        top_group = data["failure_groups"][0]

        # Verify group boundaries exist in source text
        first_line = top_group["first_seen_line"]
        assert 1 <= first_line <= len(source_lines)
        first_line_text = source_lines[first_line - 1]
        assert len(first_line_text) > 0

        # Simulate selecting an occurrence
        occ = top_group["occurrences"][0]
        start_ln = occ["start_line_number"]
        end_ln = occ["end_line_number"]
        assert 1 <= start_ln <= end_ln <= len(source_lines)

        # Build context HTML around the occurrence start line
        html = build_source_html(
            source_lines,
            highlight_primary={start_ln},
            focus_line=start_ln,
            context_radius=3,
        )
        assert str(start_ln) in html

        # Verify that invalid/hallucinated evidence (e.g. line 9999) is rejected by helper
        valid_citations = validate_line_references(
            [start_ln, 9999, -5], len(source_lines)
        )
        assert valid_citations == [start_ln]
        assert 9999 not in valid_citations

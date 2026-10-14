"""Integration and orchestrator tests for analyze_failures_with_ai."""

import json

from app.core.config import Settings
from app.services.grouping import analyze_failures
from app.services.llm.analysis_service import analyze_failures_with_ai
from app.services.llm.exceptions import LLMTimeoutError
from app.services.llm.provider_factory import MockLLMProvider
from app.services.log_parser import parse_log_text


class TestAIAnalysisServiceIntegration:
    """Integration tests verifying orchestrator, error fallbacks, and provider execution."""

    def test_successful_llm_analysis_with_mock_provider(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        # Line 8 in recurring_failures.log is:
        # "DatabaseConnectionError: Connection lost to database cluster primary"
        mock_output = json.dumps(
            {
                "summary": "AI identified recurring database connectivity issues.",
                "likely_causes": [
                    {
                        "description": "Network partition or DB pool exhaustion.",
                        "reasoning": "Repeated DatabaseConnectionError across multiple workers.",
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
                        "action": "Inspect PostgreSQL connection pool limits and health.",
                        "rationale": "High connection demand is causing connection drops.",
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
                "limitations": ["Database server-side logs were not provided."],
                "evidence_refs": [
                    {
                        "line_number": 8,
                        "excerpt": "Connection lost to database cluster primary",
                    }
                ],
            }
        )

        mock_provider = MockLLMProvider(response_text=mock_output)
        settings = Settings(LLM_ENABLED=True, LLM_PROVIDER="mock", _env_file=None)

        result = analyze_failures_with_ai(
            analysis_result=analysis,
            raw_log=recurring_failures_log_text,
            settings=settings,
            provider=mock_provider,
        )

        assert result.analysis_source == "llm"
        assert result.fallback_reason is None
        assert result.provider == "mock"
        assert result.verified_evidence_count > 0
        assert result.analysis.confidence == 0.95
        assert mock_provider.call_count == 1

    def test_markdown_code_fences_stripped_automatically(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        raw_json = json.dumps(
            {
                "summary": "Summary text",
                "likely_causes": [],
                "recommended_actions": [],
                "confidence": 0.8,
                "limitations": [],
                "evidence_refs": [
                    {
                        "line_number": 8,
                        "excerpt": "Connection lost to database cluster primary",
                    }
                ],
            }
        )
        fenced_output = f"```json\n{raw_json}\n```"
        mock_provider = MockLLMProvider(response_text=fenced_output)
        settings = Settings(LLM_ENABLED=True, LLM_PROVIDER="mock", _env_file=None)

        result = analyze_failures_with_ai(
            analysis_result=analysis,
            raw_log=recurring_failures_log_text,
            settings=settings,
            provider=mock_provider,
        )

        assert result.analysis_source == "llm"
        assert result.analysis.summary == "Summary text"

    def test_llm_disabled_triggers_immediate_fallback(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        mock_provider = MockLLMProvider()
        settings = Settings(LLM_ENABLED=False, _env_file=None)

        result = analyze_failures_with_ai(
            analysis_result=analysis,
            raw_log=recurring_failures_log_text,
            settings=settings,
            provider=mock_provider,
        )

        assert result.analysis_source == "fallback"
        assert result.fallback_reason == "LLM_DISABLED"
        assert mock_provider.call_count == 0  # Provider must NOT be called

    def test_provider_timeout_triggers_fallback(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        mock_provider = MockLLMProvider(
            simulated_exception=LLMTimeoutError(
                "Request timed out", timeout_seconds=5.0, provider="mock"
            )
        )
        settings = Settings(LLM_ENABLED=True, LLM_PROVIDER="mock", _env_file=None)

        result = analyze_failures_with_ai(
            analysis_result=analysis,
            raw_log=recurring_failures_log_text,
            settings=settings,
            provider=mock_provider,
        )

        assert result.analysis_source == "fallback"
        assert "PROVIDER_ERROR" in (result.fallback_reason or "")

    def test_invalid_json_triggers_fallback(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        mock_provider = MockLLMProvider(response_text="This is not valid json at all")
        settings = Settings(LLM_ENABLED=True, LLM_PROVIDER="mock", _env_file=None)

        result = analyze_failures_with_ai(
            analysis_result=analysis,
            raw_log=recurring_failures_log_text,
            settings=settings,
            provider=mock_provider,
        )

        assert result.analysis_source == "fallback"
        assert "INVALID_JSON" in (result.fallback_reason or "")

    def test_schema_validation_error_triggers_fallback(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        # Missing required 'summary' and invalid confidence
        invalid_schema = json.dumps(
            {
                "likely_causes": [],
                "confidence": 99.9,
            }
        )
        mock_provider = MockLLMProvider(response_text=invalid_schema)
        settings = Settings(LLM_ENABLED=True, LLM_PROVIDER="mock", _env_file=None)

        result = analyze_failures_with_ai(
            analysis_result=analysis,
            raw_log=recurring_failures_log_text,
            settings=settings,
            provider=mock_provider,
        )

        assert result.analysis_source == "fallback"
        assert "SCHEMA_VALIDATION_ERROR" in (result.fallback_reason or "")

    def test_fabricated_evidence_triggers_fallback(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        # Model hallucinates line 9999
        hallucinated_evidence = json.dumps(
            {
                "summary": "Model hallucination test",
                "likely_causes": [],
                "recommended_actions": [],
                "confidence": 0.8,
                "limitations": [],
                "evidence_refs": [
                    {
                        "line_number": 9999,
                        "excerpt": "Non-existent log line",
                    }
                ],
            }
        )
        mock_provider = MockLLMProvider(response_text=hallucinated_evidence)
        settings = Settings(LLM_ENABLED=True, LLM_PROVIDER="mock", _env_file=None)

        result = analyze_failures_with_ai(
            analysis_result=analysis,
            raw_log=recurring_failures_log_text,
            settings=settings,
            provider=mock_provider,
        )

        assert result.analysis_source == "fallback"
        assert "EVIDENCE_VERIFICATION_FAILED" in (result.fallback_reason or "")


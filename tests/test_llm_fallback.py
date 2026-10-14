"""Tests for deterministic fallback analysis generator."""

from app.services.grouping import analyze_failures
from app.services.llm.fallback import build_deterministic_fallback
from app.services.log_parser import parse_log_text


class TestDeterministicFallback:
    """Tests verifying fallback report generation when LLM is offline or disabled."""

    def test_fallback_on_recurring_failures_fixture(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        result = build_deterministic_fallback(
            analysis, recurring_failures_log_text, fallback_reason="LLM_DISABLED"
        )

        assert result.analysis_source == "fallback"
        assert result.fallback_reason == "LLM_DISABLED"
        assert result.provider == "deterministic_fallback"
        assert result.duration_seconds == 0.0

        ai = result.analysis
        assert "4 failure event(s)" in ai.summary
        assert "2 distinct failure group(s)" in ai.summary
        assert len(ai.likely_causes) == 2
        assert len(ai.recommended_actions) > 0
        assert ai.confidence == 0.5
        assert len(ai.limitations) > 0
        assert len(ai.evidence_refs) > 0

    def test_fallback_on_clean_log(self) -> None:
        clean_log = (
            "2026-10-14 10:00:00 [INFO] app: Booting up\n"
            "2026-10-14 10:00:01 [INFO] app: Ready to handle connections"
        )
        parsing = parse_log_text(clean_log)
        analysis = analyze_failures(parsing)

        result = build_deterministic_fallback(
            analysis, clean_log, fallback_reason="NO_FAILURES"
        )

        assert result.analysis_source == "fallback"
        assert result.analysis.confidence == 1.0
        assert "No error events" in result.analysis.summary
        assert len(result.analysis.likely_causes) == 0
        assert len(result.analysis.recommended_actions) == 1

    def test_fallback_is_deterministic(self, recurring_failures_log_text: str) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        res1 = build_deterministic_fallback(
            analysis, recurring_failures_log_text, fallback_reason="TEST"
        )
        res2 = build_deterministic_fallback(
            analysis, recurring_failures_log_text, fallback_reason="TEST"
        )

        # Both invocations must produce identical serialized outputs
        assert res1.model_dump_json() == res2.model_dump_json()

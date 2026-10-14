"""Tests for strict Pydantic AI analysis response schemas."""

import pytest
from pydantic import ValidationError

from app.services.llm.schemas import (
    AIAnalysis,
    AIAnalysisResult,
    EvidenceReference,
    LikelyCause,
    RecommendedAction,
)


class TestEvidenceReferenceSchema:
    """Tests for EvidenceReference schema constraints."""

    def test_valid_evidence_reference(self) -> None:
        ref = EvidenceReference(
            line_number=42,
            excerpt="Connection timed out after 5000ms",
            failure_event_id="event-1",
            fingerprint="abc12345",
        )
        assert ref.line_number == 42
        assert ref.excerpt == "Connection timed out after 5000ms"
        assert ref.failure_event_id == "event-1"
        assert ref.fingerprint == "abc12345"

    def test_zero_and_negative_line_numbers_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceReference(line_number=0, excerpt="Bad line")

        with pytest.raises(ValidationError):
            EvidenceReference(line_number=-5, excerpt="Bad line")

    def test_empty_excerpt_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceReference(line_number=1, excerpt="")

    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceReference(
                line_number=1,
                excerpt="Text",
                hallucinated_field="forbidden",  # type: ignore[call-arg]
            )


class TestLikelyCauseSchema:
    """Tests for LikelyCause schema constraints."""

    def test_valid_likely_cause(self) -> None:
        cause = LikelyCause(
            description="Database pool saturation",
            reasoning="Active connection metrics hit maximum limit.",
            evidence_refs=[EvidenceReference(line_number=10, excerpt="Pool exhausted")],
        )
        assert cause.description == "Database pool saturation"
        assert len(cause.evidence_refs) == 1

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LikelyCause(description="", reasoning="Some reasoning")


class TestRecommendedActionSchema:
    """Tests for RecommendedAction schema constraints."""

    def test_valid_priorities(self) -> None:
        for prio in ("high", "medium", "low"):
            action = RecommendedAction(
                action="Check database pool size",
                rationale="Pool may be undersized for traffic load",
                priority=prio,  # type: ignore[arg-type]
            )
            assert action.priority == prio

    def test_invalid_priority_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecommendedAction(
                action="Test",
                rationale="Test rationale",
                priority="critical",  # type: ignore[arg-type]
            )


class TestAIAnalysisSchema:
    """Tests for top-level AIAnalysis schema."""

    def test_valid_ai_analysis(self) -> None:
        analysis = AIAnalysis(
            summary="Application suffered cascading failure due to database unavailability.",
            likely_causes=[
                LikelyCause(
                    description="DB connectivity dropped",
                    reasoning="All worker threads stalled waiting for DB ack.",
                )
            ],
            recommended_actions=[
                RecommendedAction(
                    action="Check DB health",
                    rationale="Ensure cluster primary is responsive.",
                    priority="high",
                )
            ],
            confidence=0.88,
            limitations=["External query latency metrics not captured in log."],
            evidence_refs=[EvidenceReference(line_number=15, excerpt="Timeout error")],
        )
        assert analysis.confidence == 0.88
        assert len(analysis.likely_causes) == 1
        assert len(analysis.recommended_actions) == 1

    def test_confidence_bounds_enforced(self) -> None:
        base_kwargs = {
            "summary": "Summary",
            "likely_causes": [],
            "recommended_actions": [],
            "limitations": [],
            "evidence_refs": [],
        }

        # Valid boundaries
        a0 = AIAnalysis(confidence=0.0, **base_kwargs)  # type: ignore[arg-type]
        assert a0.confidence == 0.0

        a1 = AIAnalysis(confidence=1.0, **base_kwargs)  # type: ignore[arg-type]
        assert a1.confidence == 1.0

        # Invalid out of bounds
        with pytest.raises(ValidationError):
            AIAnalysis(confidence=-0.1, **base_kwargs)  # type: ignore[arg-type]

        with pytest.raises(ValidationError):
            AIAnalysis(confidence=1.05, **base_kwargs)  # type: ignore[arg-type]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            AIAnalysis(
                summary="Test",
                confidence=0.5,
                unexpected_payload={"injected": True},  # type: ignore[call-arg]
            )

    def test_container_result_model(self) -> None:
        analysis = AIAnalysis(
            summary="Summary text",
            likely_causes=[],
            recommended_actions=[],
            confidence=0.7,
            limitations=[],
            evidence_refs=[],
        )
        result = AIAnalysisResult(
            analysis=analysis,
            analysis_source="llm",
            fallback_reason=None,
            provider="openai",
            model="gpt-4o-mini",
            duration_seconds=1.23,
            verified_evidence_count=5,
        )
        assert result.analysis_source == "llm"
        assert result.provider == "openai"
        assert result.duration_seconds == 1.23
        assert result.verified_evidence_count == 5

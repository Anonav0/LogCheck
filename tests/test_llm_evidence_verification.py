"""Tests for verifying AI evidence references against source logs and supplied context."""

from app.services.llm.analysis_service import verify_ai_evidence
from app.services.llm.prompt_builder import PromptEvidenceLine
from app.services.llm.schemas import (
    AIAnalysis,
    EvidenceReference,
    LikelyCause,
    RecommendedAction,
)


def _make_dummy_analysis(refs: list[EvidenceReference]) -> AIAnalysis:
    """Helper creating minimal AIAnalysis instance containing specified references."""
    return AIAnalysis(
        summary="Test analysis",
        likely_causes=[
            LikelyCause(
                description="Test cause",
                reasoning="Test reasoning",
                evidence_refs=refs[:1],
            )
        ],
        recommended_actions=[
            RecommendedAction(
                action="Test action",
                rationale="Test rationale",
                priority="high",
                evidence_refs=refs[1:2],
            )
        ],
        confidence=0.8,
        limitations=[],
        evidence_refs=refs,
    )


class TestEvidenceVerification:
    """Tests verifying AI evidence validation against canonical source lines."""

    def test_valid_evidence_references_pass(self) -> None:
        source_lines = [
            "2026-10-14 10:00:00 [INFO] app: Booting",
            "2026-10-14 10:00:01 [ERROR] db: Connection failed to host 10.0.0.1",
            "2026-10-14 10:00:02 [INFO] app: Shutdown",
        ]
        prompt_lines = {
            2: PromptEvidenceLine(
                line_number=2,
                raw_line=source_lines[1],
                model_line=source_lines[1],
                was_redacted=False,
            )
        }
        valid_events = {"event-1"}
        valid_fps = {"fp-sha256"}

        ref = EvidenceReference(
            line_number=2,
            excerpt="Connection failed to host",
            failure_event_id="event-1",
            fingerprint="fp-sha256",
        )
        analysis = _make_dummy_analysis([ref])

        is_valid, errors = verify_ai_evidence(
            analysis=analysis,
            canonical_lines=source_lines,
            supplied_evidence_lines=prompt_lines,
            valid_event_ids=valid_events,
            valid_fingerprints=valid_fps,
        )
        assert is_valid is True
        assert len(errors) == 0

    def test_out_of_bounds_line_number_fails(self) -> None:
        source_lines = ["line 1", "line 2"]
        ref = EvidenceReference(line_number=99, excerpt="line 99")
        analysis = _make_dummy_analysis([ref])

        is_valid, errors = verify_ai_evidence(
            analysis=analysis,
            canonical_lines=source_lines,
            supplied_evidence_lines={},
            valid_event_ids=set(),
            valid_fingerprints=set(),
        )
        assert is_valid is False
        assert any("out of bounds" in e for e in errors)

    def test_fabricated_excerpt_fails(self) -> None:
        source_lines = [
            "2026-10-14 10:00:00 [INFO] worker: Starting task",
            "2026-10-14 10:00:01 [INFO] worker: Heartbeat OK",
        ]
        # Reference claims line 1 is a database crash
        ref = EvidenceReference(
            line_number=1,
            excerpt="FATAL Database corruption occurred on disk",
        )
        analysis = _make_dummy_analysis([ref])

        is_valid, errors = verify_ai_evidence(
            analysis=analysis,
            canonical_lines=source_lines,
            supplied_evidence_lines={},
            valid_event_ids=set(),
            valid_fingerprints=set(),
        )
        assert is_valid is False
        assert any("does not match source line" in e for e in errors)

    def test_unknown_event_id_fails(self) -> None:
        source_lines = ["2026-10-14 10:00:00 [ERROR] app: Task failed"]
        ref = EvidenceReference(
            line_number=1,
            excerpt="Task failed",
            failure_event_id="hallucinated-event-id-999",
        )
        analysis = _make_dummy_analysis([ref])

        is_valid, errors = verify_ai_evidence(
            analysis=analysis,
            canonical_lines=source_lines,
            supplied_evidence_lines={},
            valid_event_ids={"event-1"},
            valid_fingerprints=set(),
        )
        assert is_valid is False
        assert any("unknown failure_event_id" in e for e in errors)

    def test_unknown_fingerprint_fails(self) -> None:
        source_lines = ["2026-10-14 10:00:00 [ERROR] app: Task failed"]
        ref = EvidenceReference(
            line_number=1,
            excerpt="Task failed",
            fingerprint="unregistered-fingerprint",
        )
        analysis = _make_dummy_analysis([ref])

        is_valid, errors = verify_ai_evidence(
            analysis=analysis,
            canonical_lines=source_lines,
            supplied_evidence_lines={},
            valid_event_ids=set(),
            valid_fingerprints={"known-sha256"},
        )
        assert is_valid is False
        assert any("unknown fingerprint" in e for e in errors)

    def test_redacted_excerpt_matching(self) -> None:
        raw_line = "Connecting with client key sk-secret1234567890123456 to endpoint"
        redacted_line = "Connecting with client key [REDACTED_API_KEY] to endpoint"
        source_lines = [raw_line]

        prompt_lines = {
            1: PromptEvidenceLine(
                line_number=1,
                raw_line=raw_line,
                model_line=redacted_line,
                was_redacted=True,
            )
        }

        # Model generates reference using the redacted text it saw
        ref = EvidenceReference(
            line_number=1,
            excerpt="key [REDACTED_API_KEY] to endpoint",
        )
        analysis = _make_dummy_analysis([ref])

        is_valid, errors = verify_ai_evidence(
            analysis=analysis,
            canonical_lines=source_lines,
            supplied_evidence_lines=prompt_lines,
            valid_event_ids=set(),
            valid_fingerprints=set(),
        )
        assert is_valid is True
        assert len(errors) == 0


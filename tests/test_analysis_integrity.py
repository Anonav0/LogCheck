"""End-to-end and defensive tests for analysis and evidence integrity in LogLens AI."""

from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.exceptions import EvidenceIntegrityError, InputValidationError
from app.services.evidence_validator import (
    run_validated_analysis,
    validate_analysis_result,
)


class TestE2EValidatedAnalysisFixtures:
    """End-to-end tests for run_validated_analysis across all canonical fixtures."""

    def test_sample_application_log_integrity(
        self, sample_application_log_text: str
    ) -> None:
        analysis = run_validated_analysis(sample_application_log_text)
        integrity = validate_analysis_result(sample_application_log_text, analysis)
        assert integrity.is_valid is True
        assert len(integrity.errors) == 0
        assert integrity.validated_lines_count == len(analysis.parsing_result.entries)
        assert integrity.validated_events_count == len(
            analysis.parsing_result.failure_events
        )
        assert integrity.validated_groups_count == len(analysis.failure_groups)
        assert integrity.validated_lines_count > 0
        assert integrity.validated_events_count > 0
        assert integrity.validated_groups_count > 0

    def test_sample_test_failure_log_integrity(
        self, sample_test_failure_log_text: str
    ) -> None:
        analysis = run_validated_analysis(sample_test_failure_log_text)
        integrity = validate_analysis_result(sample_test_failure_log_text, analysis)
        assert integrity.is_valid is True
        assert len(integrity.errors) == 0
        assert integrity.validated_lines_count == len(analysis.parsing_result.entries)
        assert integrity.validated_events_count == len(
            analysis.parsing_result.failure_events
        )
        assert integrity.validated_groups_count == len(analysis.failure_groups)

    def test_recurring_failures_log_integrity(
        self, recurring_failures_log_text: str
    ) -> None:
        analysis = run_validated_analysis(recurring_failures_log_text)
        integrity = validate_analysis_result(recurring_failures_log_text, analysis)
        assert integrity.is_valid is True
        assert len(integrity.errors) == 0
        assert integrity.validated_lines_count == len(analysis.parsing_result.entries)
        assert integrity.validated_events_count == len(
            analysis.parsing_result.failure_events
        )
        assert integrity.validated_groups_count == len(analysis.failure_groups)

    def test_malformed_log_integrity(self, malformed_log_text: str) -> None:
        analysis = run_validated_analysis(malformed_log_text)
        integrity = validate_analysis_result(malformed_log_text, analysis)
        assert integrity.is_valid is True
        assert len(integrity.errors) == 0
        assert integrity.validated_lines_count == len(analysis.parsing_result.entries)

    def test_clean_log_without_errors(self) -> None:
        clean_log = (
            "2026-10-14 10:00:00 [INFO] app: Booted\n"
            "2026-10-14 10:00:01 [INFO] app: Ready to serve traffic"
        )
        analysis = run_validated_analysis(clean_log)
        integrity = validate_analysis_result(clean_log, analysis)
        assert integrity.is_valid is True
        assert integrity.validated_lines_count == 2
        assert integrity.validated_events_count == 0
        assert integrity.validated_groups_count == 0
        assert analysis.metrics.total_failure_events == 0
        assert len(analysis.failure_groups) == 0


class TestDefensiveBehaviorAndEarlyRejection:
    """Tests ensuring rejected inputs do not invoke the parser or downstream analysis."""

    def test_empty_input_rejected_before_parsing(self) -> None:
        with patch("app.services.evidence_validator.parse_log_text") as mock_parse:
            with pytest.raises(InputValidationError) as exc_info:
                run_validated_analysis("")
            assert exc_info.value.code == "EMPTY_LOG_INPUT"
            mock_parse.assert_not_called()

    def test_oversized_bytes_rejected_before_parsing(self) -> None:
        settings = Settings(MAX_LOG_SIZE_BYTES=10, _env_file=None)
        with patch("app.services.evidence_validator.parse_log_text") as mock_parse:
            with pytest.raises(InputValidationError) as exc_info:
                run_validated_analysis("12345678901", settings=settings)
            assert exc_info.value.code == "LOG_TOO_LARGE"
            mock_parse.assert_not_called()

    def test_oversized_lines_rejected_before_parsing(self) -> None:
        settings = Settings(MAX_LOG_LINES=2, _env_file=None)
        with patch("app.services.evidence_validator.parse_log_text") as mock_parse:
            with pytest.raises(InputValidationError) as exc_info:
                run_validated_analysis("line1\nline2\nline3", settings=settings)
            assert exc_info.value.code == "TOO_MANY_LOG_LINES"
            mock_parse.assert_not_called()

    def test_oversized_single_line_rejected_before_parsing(self) -> None:
        settings = Settings(MAX_LOG_LINE_LENGTH=5, _env_file=None)
        with patch("app.services.evidence_validator.parse_log_text") as mock_parse:
            with pytest.raises(InputValidationError) as exc_info:
                run_validated_analysis("toolong", settings=settings)
            assert exc_info.value.code == "LOG_LINE_TOO_LONG"
            mock_parse.assert_not_called()


class TestTamperingDetectionOnAnalysisResult:
    """Tests verifying that tampered AnalysisResult fields fail evidence validation."""

    def test_tampered_group_count_detected(
        self, sample_application_log_text: str
    ) -> None:
        analysis = run_validated_analysis(sample_application_log_text)

        # Mutate occurrence_count on the first group
        mutated_group = analysis.failure_groups[0].model_copy(
            update={"occurrence_count": 9999}
        )
        mutated_groups = [mutated_group] + list(analysis.failure_groups[1:])
        tampered_analysis = analysis.model_copy(
            update={"failure_groups": mutated_groups}
        )

        integrity = validate_analysis_result(
            sample_application_log_text, tampered_analysis
        )
        assert integrity.is_valid is False
        assert any(
            issue.code == "OCCURRENCE_COUNT_MISMATCH" for issue in integrity.errors
        )

    def test_tampered_first_seen_line_detected(
        self, sample_application_log_text: str
    ) -> None:
        analysis = run_validated_analysis(sample_application_log_text)

        mutated_group = analysis.failure_groups[0].model_copy(
            update={"first_seen_line": 9999}
        )
        mutated_groups = [mutated_group] + list(analysis.failure_groups[1:])
        tampered_analysis = analysis.model_copy(
            update={"failure_groups": mutated_groups}
        )

        integrity = validate_analysis_result(
            sample_application_log_text, tampered_analysis
        )
        assert integrity.is_valid is False
        assert any(
            issue.code == "FIRST_SEEN_LINE_MISMATCH" for issue in integrity.errors
        )

    def test_tampered_fingerprint_format_detected(
        self, sample_application_log_text: str
    ) -> None:
        analysis = run_validated_analysis(sample_application_log_text)

        mutated_group = analysis.failure_groups[0].model_copy(
            update={"fingerprint": "invalid-sha"}
        )
        mutated_groups = [mutated_group] + list(analysis.failure_groups[1:])
        tampered_analysis = analysis.model_copy(
            update={"failure_groups": mutated_groups}
        )

        integrity = validate_analysis_result(
            sample_application_log_text, tampered_analysis
        )
        assert integrity.is_valid is False
        assert any(
            issue.code == "INVALID_FINGERPRINT_FORMAT" for issue in integrity.errors
        )

    def test_tampered_aggregate_metrics_detected(
        self, sample_application_log_text: str
    ) -> None:
        analysis = run_validated_analysis(sample_application_log_text)

        mutated_metrics = analysis.metrics.model_copy(
            update={"total_failure_events": analysis.metrics.total_failure_events + 50}
        )
        tampered_analysis = analysis.model_copy(update={"metrics": mutated_metrics})

        integrity = validate_analysis_result(
            sample_application_log_text, tampered_analysis
        )
        assert integrity.is_valid is False
        assert any(
            issue.code == "METRIC_TOTAL_EVENTS_MISMATCH" for issue in integrity.errors
        )

    def test_run_validated_analysis_raises_evidence_integrity_error(
        self, sample_application_log_text: str
    ) -> None:
        from app.models.validation_result import (
            EvidenceValidationResult,
            ValidationIssue,
        )

        simulated_failure = EvidenceValidationResult(
            is_valid=False,
            errors=[
                ValidationIssue(
                    code="CORRUPTED_LINE_REFERENCE",
                    message="Simulated corrupt line reference",
                    line_number=42,
                    entity_id="sim-1",
                )
            ],
            warnings=[],
            validated_lines_count=0,
            validated_events_count=0,
            validated_groups_count=0,
        )

        with patch(
            "app.services.evidence_validator.validate_analysis_result",
            return_value=simulated_failure,
        ):
            with pytest.raises(EvidenceIntegrityError) as exc_info:
                run_validated_analysis(sample_application_log_text)
            assert exc_info.value.code == "CORRUPTED_LINE_REFERENCE"
            assert exc_info.value.line_number == 42
            assert exc_info.value.entity_id == "sim-1"

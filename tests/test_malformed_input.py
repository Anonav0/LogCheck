"""Tests for handling malformed, unstructured, and edge-case log input in LogLens AI."""

import pytest

from app.core.exceptions import InputValidationError
from app.models import LineCategory, LogLevel
from app.services.evidence_validator import (
    run_validated_analysis,
    validate_analysis_result,
    validate_parsing_result,
)
from app.services.input_validator import validate_log_input
from app.services.log_parser import parse_log_text


class TestMalformedTimestamps:
    """Tests ensuring malformed or impossible timestamps do not crash the pipeline."""

    def test_impossible_timestamp_does_not_crash(self) -> None:
        log_text = "2026-99-99 25:61:99 [ERROR] system: Corrupted timestamp header"
        validated = validate_log_input(log_text)
        assert validated.is_valid is True
        assert validated.line_count == 1

        result = parse_log_text(log_text)
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.line_number == 1
        assert entry.level == LogLevel.ERROR

        integrity = validate_parsing_result(log_text, result)
        assert integrity.is_valid is True


class TestMalformedJsonLines:
    """Tests ensuring truncated or invalid JSON log lines are preserved without crashing."""

    def test_truncated_json_line_is_preserved(self) -> None:
        log_text = (
            '{"timestamp": "2026-10-14T09:00:00", "level": "INFO", "message": "Good line"}\n'
            '{"level": "ERROR", "message": "Truncated json line\n'
            '{"timestamp": "2026-10-14T09:00:02", "level": "WARN", "message": "Another line"}'
        )
        validated = validate_log_input(log_text)
        assert validated.is_valid is True
        assert validated.line_count == 3

        result = parse_log_text(log_text)
        assert len(result.entries) == 3
        # Truncated json line should be kept as an entry, level may be inferred or None
        assert result.entries[1].line_number == 2
        assert '{"level": "ERROR"' in result.entries[1].raw_line

        integrity = validate_parsing_result(log_text, result)
        assert integrity.is_valid is True

    def test_malformed_json_syntax_preserved(self) -> None:
        log_text = '{"key": undefined, [1, 2, 3]: error}'
        validated = validate_log_input(log_text)
        assert validated.is_valid is True

        result = parse_log_text(log_text)
        assert len(result.entries) == 1
        assert result.entries[0].level is None

        integrity = validate_parsing_result(log_text, result)
        assert integrity.is_valid is True


class TestUnknownAndUnstructuredFormats:
    """Tests ensuring arbitrary unstructured logs and legacy scripts process smoothly."""

    def test_completely_unstructured_text(self) -> None:
        log_text = (
            "Starting script runner v1.0\n"
            "Executing task step 1...\n"
            "All tasks completed successfully."
        )
        validated = validate_log_input(log_text)
        assert validated.is_valid is True

        result = parse_log_text(log_text)
        assert len(result.entries) == 3
        for i, entry in enumerate(result.entries, start=1):
            assert entry.line_number == i
            assert entry.level is None
            assert entry.category == LineCategory.UNKNOWN

        integrity = validate_parsing_result(log_text, result)
        assert integrity.is_valid is True

    def test_benign_messages_containing_error_keywords(self) -> None:
        log_text = (
            "Note: The error handling policy has been updated successfully for all worker queues.\n"
            "System operational with 0 errors reported during baseline audit verification."
        )
        validated = validate_log_input(log_text)
        assert validated.is_valid is True

        result = parse_log_text(log_text)
        assert len(result.entries) == 2
        # Should not falsely create unverified crash traces
        integrity = validate_parsing_result(log_text, result)
        assert integrity.is_valid is True

    def test_malformed_log_fixture_e2e(self, malformed_log_text: str) -> None:
        validated = validate_log_input(malformed_log_text)
        assert validated.is_valid is True

        analysis_result = run_validated_analysis(malformed_log_text)
        integrity = validate_analysis_result(malformed_log_text, analysis_result)
        assert integrity.is_valid is True
        assert len(integrity.errors) == 0
        assert integrity.validated_lines_count == len(
            analysis_result.parsing_result.entries
        )


class TestUnicodePreservation:
    """Tests ensuring multibyte Unicode and non-ASCII characters are preserved without corruption."""

    def test_multilingual_and_emoji_characters(self) -> None:
        log_text = (
            "2026-10-14 10:00:00 [INFO] 🚀 Service started successfully\n"
            "2026-10-14 10:00:01 [WARN] 警告: メモリ使用量が高いです\n"
            "2026-10-14 10:00:02 [ERROR] خطأ في الاتصال بقاعدة البيانات\n"
            "2026-10-14 10:00:03 [INFO] Все сервисы работают в штатном режиме"
        )
        validated = validate_log_input(log_text)
        assert validated.is_valid is True
        assert validated.line_count == 4

        result = parse_log_text(log_text)
        assert len(result.entries) == 4
        assert "🚀 Service started successfully" in result.entries[0].message
        assert "メモリ使用量が高いです" in result.entries[1].message
        assert result.entries[1].logger_name == "警告"
        assert "خطأ في الاتصال بقاعدة البيانات" in result.entries[2].message
        assert "Все сервисы работают в штатном режиме" in result.entries[3].message

        integrity = validate_parsing_result(log_text, result)
        assert integrity.is_valid is True

    def test_surrogate_code_points_rejected(self) -> None:
        surrogate_string = "Error occurred: \ud800 in module"
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(surrogate_string)
        assert exc_info.value.code == "INVALID_ENCODING"


class TestEmptyLinesHandling:
    """Tests ensuring empty lines retain exact positioning and do not distort line numbering."""

    def test_interspersed_empty_lines_preserve_numbering(self) -> None:
        log_text = (
            "2026-10-14 10:00:00 [INFO] Line one\n"
            "\n"
            "2026-10-14 10:00:02 [ERROR] Line three\n"
            "\n"
            "2026-10-14 10:00:04 [INFO] Line five"
        )
        validated = validate_log_input(log_text)
        assert validated.is_valid is True
        assert validated.line_count == 5

        result = parse_log_text(log_text)
        assert len(result.entries) == 5
        assert result.entries[0].line_number == 1
        assert result.entries[1].line_number == 2
        assert result.entries[1].raw_line == ""
        assert result.entries[2].line_number == 3
        assert result.entries[3].line_number == 4
        assert result.entries[3].raw_line == ""
        assert result.entries[4].line_number == 5

        integrity = validate_parsing_result(log_text, result)
        assert integrity.is_valid is True
        assert integrity.validated_lines_count == 5

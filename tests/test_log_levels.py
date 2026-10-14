"""Tests for log severity recognition, normalization, and false-positive prevention."""

import pytest

from app.models.log_entry import LineCategory, LogLevel, normalize_log_level
from app.services.log_parser import parse_log_text


class TestLogLevelNormalization:
    """Verify normalizations of raw severity strings to canonical LogLevel."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("WARN", LogLevel.WARNING),
            ("WARNING", LogLevel.WARNING),
            ("warn", LogLevel.WARNING),
            ("FATAL", LogLevel.CRITICAL),
            ("CRITICAL", LogLevel.CRITICAL),
            ("critical", LogLevel.CRITICAL),
            ("ERROR", LogLevel.ERROR),
            ("error", LogLevel.ERROR),
            ("INFO", LogLevel.INFO),
            ("DEBUG", LogLevel.DEBUG),
            ("TRACE", LogLevel.TRACE),
            ("UNKNOWN", None),
            ("", None),
            (None, None),
        ],
    )
    def test_normalize_log_level(
        self, raw: str | None, expected: LogLevel | None
    ) -> None:
        """Verify normalizations from raw strings to LogLevel enum members."""
        assert normalize_log_level(raw) == expected


class TestLogLevelDetectionInLogLines:
    """Verify level extraction across various real-world line formats."""

    def test_standard_bracketed_level(self) -> None:
        """Verify bracketed level extraction."""
        log = "2026-10-14 08:30:01,102 [INFO] app.server: Starting worker"
        result = parse_log_text(log)
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.level == LogLevel.INFO
        assert entry.category == LineCategory.NORMAL
        assert entry.logger_name == "app.server"
        assert entry.message == "Starting worker"

    def test_warn_normalized_to_warning_in_text(self) -> None:
        """Verify WARN is normalized to WARNING."""
        log = "2026-10-14 08:30:02 [WARN] app.cache: Cache timeout"
        result = parse_log_text(log)
        assert result.entries[0].level == LogLevel.WARNING
        assert result.entries[0].category == LineCategory.WARNING
        assert result.warning_count == 1

    def test_fatal_normalized_to_critical_in_text(self) -> None:
        """Verify FATAL is normalized to CRITICAL."""
        log = "2026-10-14 08:30:03 [FATAL] app.core: Process dying"
        result = parse_log_text(log)
        assert result.entries[0].level == LogLevel.CRITICAL
        assert result.entries[0].category == LineCategory.ERROR
        assert result.error_count == 1

    def test_spaced_level_format(self) -> None:
        """Verify timestamp + level + logger - message format."""
        log = "2026-10-14 10:15:30 INFO application.worker - Job started"
        result = parse_log_text(log)
        entry = result.entries[0]
        assert entry.level == LogLevel.INFO
        assert entry.logger_name == "application.worker"
        assert entry.message == "Job started"

    def test_prefix_level_format(self) -> None:
        """Verify LEVEL: message format."""
        log = "ERROR: Unable to connect to host"
        result = parse_log_text(log)
        entry = result.entries[0]
        assert entry.level == LogLevel.ERROR
        assert entry.message == "Unable to connect to host"
        assert result.error_count == 1

    def test_info_containing_word_error_remains_info(self) -> None:
        """Verify message text containing 'error' does not cause misclassification."""
        log = "2026-10-14 10:00:00 [INFO] app.recovery: The previous error has been resolved"
        result = parse_log_text(log)
        entry = result.entries[0]
        assert entry.level == LogLevel.INFO
        assert entry.category == LineCategory.NORMAL
        assert result.error_count == 0
        assert result.failure_event_count == 0

    def test_info_containing_word_warning_remains_info(self) -> None:
        """Verify message text containing 'warning' does not become WARNING."""
        log = "2026-10-14 10:00:00 [INFO] app.monitor: Updated warning threshold"
        result = parse_log_text(log)
        entry = result.entries[0]
        assert entry.level == LogLevel.INFO
        assert entry.category == LineCategory.NORMAL
        assert result.warning_count == 0

    def test_json_log_line_parsing(self) -> None:
        """Verify structured JSON log lines are parsed accurately."""
        log = '{"timestamp": "2026-10-14T11:00:00Z", "level": "ERROR", "logger": "billing.svc", "message": "Card declined"}'
        result = parse_log_text(log)
        entry = result.entries[0]
        assert entry.level == LogLevel.ERROR
        assert entry.logger_name == "billing.svc"
        assert entry.message == "Card declined"
        assert entry.timestamp == "2026-10-14T11:00:00Z"
        assert result.error_count == 1

    def test_malformed_json_line_handled_gracefully(self) -> None:
        """Verify invalid JSON does not crash parser and is preserved as raw text."""
        log = '{"level": "ERROR", "message": "Unterminated JSON string'
        result = parse_log_text(log)
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.raw_line == log
        assert entry.category == LineCategory.UNKNOWN

    def test_malformed_timestamp_does_not_crash(self) -> None:
        """Verify line with corrupted timestamp does not crash parser."""
        log = "2026-99-99 25:61:99 [UNKNOWN_LEVEL] system.kernel: System clock drift"
        result = parse_log_text(log)
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.line_number == 1
        assert "System clock drift" in entry.raw_line

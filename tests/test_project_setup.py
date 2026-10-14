"""Tests for Phase 1 project setup, configuration, and sample log fixtures."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.main import get_app_info


class TestProjectConfiguration:
    """Verify application configuration defaults, imports, and validation."""

    def test_configuration_can_be_imported(self) -> None:
        """Verify that Settings and get_settings can be imported successfully."""
        assert Settings is not None
        assert callable(get_settings)

    def test_default_application_name(self, clean_settings: Settings) -> None:
        """Verify default application name is 'LogLens AI'."""
        assert clean_settings.APP_NAME == "LogLens AI"
        assert clean_settings.APP_ENV == "development"
        assert clean_settings.DEBUG is False

    def test_default_log_size_and_line_limits_are_positive(
        self, clean_settings: Settings
    ) -> None:
        """Verify default log processing limits are positive values."""
        assert clean_settings.MAX_LOG_SIZE_BYTES > 0
        assert clean_settings.MAX_LOG_SIZE_BYTES == 1_048_576  # 1 MiB
        assert clean_settings.MAX_LOG_LINES > 0
        assert clean_settings.MAX_LOG_LINES == 20_000

    def test_llm_disabled_by_default(self, clean_settings: Settings) -> None:
        """Verify LLM-assisted analysis is disabled by default."""
        assert clean_settings.LLM_ENABLED is False

    def test_optional_llm_credentials_not_required(
        self, clean_settings: Settings
    ) -> None:
        """Verify LLM credentials and provider configurations are optional."""
        assert clean_settings.LLM_PROVIDER is None
        assert clean_settings.LLM_API_KEY is None
        assert clean_settings.LLM_MODEL is None
        assert clean_settings.LLM_TIMEOUT_SECONDS > 0
        assert clean_settings.LLM_TIMEOUT_SECONDS == 30.0

    @pytest.mark.parametrize(
        ("invalid_field", "invalid_value"),
        [
            ("MAX_LOG_SIZE_BYTES", 0),
            ("MAX_LOG_SIZE_BYTES", -1024),
            ("MAX_LOG_LINES", 0),
            ("MAX_LOG_LINES", -100),
            ("LLM_TIMEOUT_SECONDS", 0.0),
            ("LLM_TIMEOUT_SECONDS", -5.0),
        ],
    )
    def test_configuration_rejects_invalid_limits_or_timeouts(
        self, invalid_field: str, invalid_value: int | float
    ) -> None:
        """Verify that negative or zero limits and timeouts raise ValidationError."""
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{invalid_field: invalid_value})

    def test_get_app_info_metadata(self, clean_settings: Settings) -> None:
        """Verify main entry point returns expected application metadata."""
        info = get_app_info()
        assert info["app_name"] == "LogLens AI"
        assert info["status"] == "scaffolding_ready"

    def test_main_module_execution(self) -> None:
        """Verify executing main module as a standalone script prints application status."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "app.main"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Initialized LogLens AI" in result.stdout
        assert "Status: scaffolding_ready" in result.stdout


class TestSampleLogFixtures:
    """Verify sample log fixtures existence, format, and required characteristics."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "sample_application.log",
            "sample_test_failure.log",
            "recurring_failures.log",
            "malformed.log",
        ],
    )
    def test_required_fixtures_exist(
        self, fixtures_dir: Path, fixture_name: str
    ) -> None:
        """Verify that every required fixture file exists on disk."""
        fixture_path = fixtures_dir / fixture_name
        assert fixture_path.is_file(), f"Expected fixture {fixture_name} to exist"

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "sample_application.log",
            "sample_test_failure.log",
            "recurring_failures.log",
            "malformed.log",
        ],
    )
    def test_fixtures_are_valid_utf8(
        self, fixtures_dir: Path, fixture_name: str
    ) -> None:
        """Verify all fixture files can be decoded cleanly as UTF-8."""
        fixture_path = fixtures_dir / fixture_name
        content = fixture_path.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_sample_application_log_structure(
        self, sample_application_log_text: str
    ) -> None:
        """Verify sample_application.log includes INFO, WARNING, DB error, and traceback."""
        assert "[INFO]" in sample_application_log_text
        assert "[WARNING]" in sample_application_log_text
        assert "[ERROR]" in sample_application_log_text
        assert "Traceback (most recent call last):" in sample_application_log_text
        assert "ConnectionTimeoutError" in sample_application_log_text
        # Ensure there is a subsequent log entry after traceback
        lines = sample_application_log_text.strip().splitlines()
        last_line = lines[-1]
        assert "[INFO]" in last_line

    def test_sample_test_failure_log_structure(
        self, sample_test_failure_log_text: str
    ) -> None:
        """Verify sample_test_failure.log includes test output, failures, and summary."""
        assert "test session starts" in sample_test_failure_log_text
        assert "FAILED" in sample_test_failure_log_text
        assert "AssertionError" in sample_test_failure_log_text
        assert "short test summary info" in sample_test_failure_log_text
        assert "1 failed, 4 passed" in sample_test_failure_log_text

    def test_recurring_failures_log_structure(
        self, recurring_failures_log_text: str
    ) -> None:
        """Verify recurring_failures.log contains repeated failures and variable identifiers."""
        # Check repeated logical failure: DatabaseConnectionError occurs at least 3 times
        db_error_count = recurring_failures_log_text.count("DatabaseConnectionError")
        assert db_error_count >= 3, (
            f"Expected at least 3 occurrences of DatabaseConnectionError, got {db_error_count}"
        )

        # Check variable request IDs across failures
        assert "req-a1b2c3d4" in recurring_failures_log_text
        assert "req-e5f6g7h8" in recurring_failures_log_text
        assert "req-11223344" in recurring_failures_log_text

        # Check at least one different exception type is present
        assert "ValidationError" in recurring_failures_log_text

    def test_malformed_log_structure(self, malformed_log_text: str) -> None:
        """Verify malformed.log contains malformed timestamps, unstructured lines, and non-error text."""
        # Corrupted timestamp
        assert "2026-99-99 25:61:99" in malformed_log_text

        # Unstructured line
        assert "completely unstructured line" in malformed_log_text

        # Empty lines present in the text
        lines = malformed_log_text.splitlines()
        assert any(len(line.strip()) == 0 for line in lines)

        # Informational line containing the word "error" that is not a failure
        assert (
            "error handling policy has been updated successfully" in malformed_log_text
        )
        assert "0 errors reported" in malformed_log_text

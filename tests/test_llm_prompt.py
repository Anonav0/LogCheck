"""Tests for LLM prompt builder, evidence selection limits, and secret redaction."""

from app.core.config import Settings
from app.services.grouping import analyze_failures
from app.services.llm.prompt_builder import (
    build_analysis_prompt,
    redact_sensitive_content,
)
from app.services.log_parser import parse_log_text


class TestSecretRedaction:
    """Tests for conservative secret and credential redaction in prompt builder."""

    def test_redact_api_key(self) -> None:
        raw = "Connecting with client key sk-abc12345678901234567890 to backend"
        redacted, modified = redact_sensitive_content(raw)
        assert modified is True
        assert "[REDACTED_API_KEY]" in redacted
        assert "sk-abc12345678901234567890" not in redacted

    def test_redact_bearer_token(self) -> None:
        raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"
        redacted, modified = redact_sensitive_content(raw)
        assert modified is True
        assert "Bearer [REDACTED_TOKEN]" in redacted

    def test_redact_password_assignment(self) -> None:
        raw = 'database_connect(user="admin", password="super_secret_pw123", host="localhost")'
        redacted, modified = redact_sensitive_content(raw)
        assert modified is True
        assert 'password="[REDACTED]"' in redacted
        assert "super_secret_pw123" not in redacted

    def test_redact_private_key_block(self) -> None:
        raw = (
            "Loaded key:\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Yq...\n"
            "-----END RSA PRIVATE KEY-----\n"
            "Ready."
        )
        redacted, modified = redact_sensitive_content(raw)
        assert modified is True
        assert "[REDACTED_PRIVATE_KEY]" in redacted
        assert "MIIEowIBAAKCAQEA0Yq..." not in redacted

    def test_benign_log_remains_unmodified(self) -> None:
        raw = (
            "2026-10-14 10:00:00 [INFO] app.server: Starting worker pool with 4 threads"
        )
        redacted, modified = redact_sensitive_content(raw)
        assert modified is False
        assert redacted == raw


class TestPromptConstruction:
    """Tests for bounded prompt construction from failure analysis results."""

    def test_prompt_contains_failure_and_evidence(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        built_prompt = build_analysis_prompt(analysis, recurring_failures_log_text)

        assert "<LOG_EVIDENCE>" in built_prompt.prompt_text
        assert "</LOG_EVIDENCE>" in built_prompt.prompt_text
        assert "DatabaseConnectionError" in built_prompt.prompt_text
        assert len(built_prompt.evidence_lines) > 0
        assert built_prompt.total_source_lines == parsing.total_lines

    def test_group_limit_enforced(self, recurring_failures_log_text: str) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)
        assert len(analysis.failure_groups) == 2

        # Configure max 1 group
        settings = Settings(LLM_MAX_FAILURE_GROUPS=1, _env_file=None)
        built_prompt = build_analysis_prompt(
            analysis, recurring_failures_log_text, settings=settings
        )

        assert built_prompt.omitted_groups_count == 1
        # The higher recurrence group (DatabaseConnectionError) should be selected
        assert "DatabaseConnectionError" in built_prompt.prompt_text

    def test_evidence_line_limit_enforced(
        self, sample_application_log_text: str
    ) -> None:
        parsing = parse_log_text(sample_application_log_text)
        analysis = analyze_failures(parsing)

        settings = Settings(LLM_MAX_EVIDENCE_LINES=3, _env_file=None)
        built_prompt = build_analysis_prompt(
            analysis, sample_application_log_text, settings=settings
        )

        assert len(built_prompt.evidence_lines) <= 3

    def test_prompt_character_limit_enforced(
        self, sample_application_log_text: str
    ) -> None:
        parsing = parse_log_text(sample_application_log_text)
        analysis = analyze_failures(parsing)

        # Restrict prompt character limit
        settings = Settings(LLM_MAX_PROMPT_CHARS=2500, _env_file=None)
        built_prompt = build_analysis_prompt(
            analysis, sample_application_log_text, settings=settings
        )

        assert len(built_prompt.prompt_text) <= 2500

    def test_original_log_unaltered_by_prompt_construction(
        self, recurring_failures_log_text: str
    ) -> None:
        parsing = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing)

        original_copy = str(recurring_failures_log_text)
        built_prompt = build_analysis_prompt(analysis, recurring_failures_log_text)

        # Assert no side-effects on original string
        assert recurring_failures_log_text == original_copy
        assert built_prompt.total_source_lines == len(original_copy.splitlines())

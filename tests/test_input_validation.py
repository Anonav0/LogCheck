"""Tests for input validation: types, emptiness, byte limits, line counts, and file uploads."""

import pytest

from app.core.config import Settings
from app.core.exceptions import InputValidationError
from app.services.input_validator import (
    validate_log_file_bytes,
    validate_log_input,
)


class TestInputTypeAndEmptiness:
    """Verify type constraints and rejection of blank/whitespace payloads."""

    def test_valid_multiline_input_accepted(self) -> None:
        """Verify normal multiline log text validates successfully."""
        raw = (
            "2026-10-14 10:00:00 [INFO] app: Start\n2026-10-14 10:00:01 [INFO] app: End"
        )
        validated = validate_log_input(raw)
        assert validated.is_valid is True
        assert validated.raw_text == raw
        assert validated.line_count == 2
        assert validated.byte_size == len(raw.encode("utf-8"))

    @pytest.mark.parametrize(
        "empty_input",
        [
            "",
            "   ",
            "\n",
            "\t\n  \r\n",
            "   \n\n   \n",
        ],
    )
    def test_empty_and_whitespace_only_rejected(self, empty_input: str) -> None:
        """Verify empty and whitespace/newline-only inputs raise EMPTY_LOG_INPUT."""
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(empty_input)
        assert exc_info.value.code == "EMPTY_LOG_INPUT"

    @pytest.mark.parametrize(
        "invalid_type_input",
        [
            None,
            12345,
            3.14,
            ["2026-10-14 10:00:00 [INFO] log line"],
            {"log": "content"},
            b"bytes are not str",
        ],
    )
    def test_non_string_types_rejected(self, invalid_type_input: object) -> None:
        """Verify non-string types raise INVALID_INPUT_TYPE without implicit conversion."""
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(invalid_type_input)  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_INPUT_TYPE"

    def test_leading_and_trailing_blank_lines_preserved_in_valid_log(self) -> None:
        """Verify blank lines in an otherwise valid log are preserved in raw_text."""
        raw = "\n2026-10-14 10:00:00 [INFO] app: Started\n\n"
        validated = validate_log_input(raw)
        assert validated.is_valid is True
        assert validated.raw_text == raw
        assert validated.line_count == 3


class TestInputSizeLimits:
    """Verify UTF-8 byte limits and line count thresholds."""

    def test_input_exactly_at_byte_limit_accepted(self) -> None:
        """Verify input whose UTF-8 byte count equals MAX_LOG_SIZE_BYTES is accepted."""
        settings = Settings(_env_file=None, MAX_LOG_SIZE_BYTES=100)
        exact_text = "a" * 100
        validated = validate_log_input(exact_text, settings=settings)
        assert validated.byte_size == 100

    def test_input_exceeding_byte_limit_by_one_rejected(self) -> None:
        """Verify input exceeding MAX_LOG_SIZE_BYTES by 1 byte raises LOG_TOO_LARGE."""
        settings = Settings(_env_file=None, MAX_LOG_SIZE_BYTES=100)
        oversized = "a" * 101
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(oversized, settings=settings)
        assert exc_info.value.code == "LOG_TOO_LARGE"
        assert exc_info.value.limit == 100
        assert exc_info.value.actual == 101

    def test_multibyte_unicode_measured_by_utf8_bytes(self) -> None:
        """Verify Unicode characters are measured by UTF-8 encoded bytes, not char count."""
        # '€' is 1 char, but 3 bytes in UTF-8
        settings = Settings(_env_file=None, MAX_LOG_SIZE_BYTES=10)
        # 3 euro signs = 9 bytes (accepted)
        val = validate_log_input("€€€", settings=settings)
        assert val.byte_size == 9

        # 4 euro signs = 12 bytes (exceeds 10 bytes -> rejected)
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input("€€€€", settings=settings)
        assert exc_info.value.code == "LOG_TOO_LARGE"
        assert exc_info.value.actual == 12

    def test_input_exactly_at_line_limit_accepted(self) -> None:
        """Verify input whose line count equals MAX_LOG_LINES is accepted."""
        settings = Settings(_env_file=None, MAX_LOG_LINES=5)
        raw = "line1\nline2\nline3\nline4\nline5"
        validated = validate_log_input(raw, settings=settings)
        assert validated.line_count == 5

    def test_input_exceeding_line_limit_rejected(self) -> None:
        """Verify input exceeding MAX_LOG_LINES raises TOO_MANY_LOG_LINES."""
        settings = Settings(_env_file=None, MAX_LOG_LINES=5)
        raw = "line1\nline2\nline3\nline4\nline5\nline6"
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(raw, settings=settings)
        assert exc_info.value.code == "TOO_MANY_LOG_LINES"
        assert exc_info.value.limit == 5
        assert exc_info.value.actual == 6

    def test_line_exactly_at_character_length_limit_accepted(self) -> None:
        """Verify line with len == MAX_LOG_LINE_LENGTH is accepted."""
        settings = Settings(_env_file=None, MAX_LOG_LINE_LENGTH=50)
        line = "x" * 50
        validated = validate_log_input(line, settings=settings)
        assert validated.is_valid is True

    def test_line_exceeding_character_length_limit_rejected(self) -> None:
        """Verify line with len > MAX_LOG_LINE_LENGTH raises LOG_LINE_TOO_LONG with line_number."""
        settings = Settings(_env_file=None, MAX_LOG_LINE_LENGTH=50)
        raw = f"short line 1\n{'x' * 51}\nshort line 3"
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(raw, settings=settings)
        assert exc_info.value.code == "LOG_LINE_TOO_LONG"
        assert exc_info.value.line_number == 2
        assert exc_info.value.limit == 50
        assert exc_info.value.actual == 51


class TestFileUploadValidation:
    """Verify validation of uploaded file byte streams."""

    def test_valid_file_bytes_accepted(self) -> None:
        """Verify valid UTF-8 file bytes decode and validate."""
        content = "2026-10-14 10:00:00 [INFO] app: File test"
        data = content.encode("utf-8")
        val = validate_log_file_bytes(data)
        assert val.raw_text == content
        assert val.line_count == 1

    def test_utf8_bom_handled_and_stripped(self) -> None:
        """Verify UTF-8 Byte Order Mark (\xef\xbb\xbf) is stripped cleanly without corruption."""
        content = "2026-10-14 10:00:00 [INFO] app: BOM test"
        data = b"\xef\xbb\xbf" + content.encode("utf-8")
        val = validate_log_file_bytes(data)
        assert val.raw_text == content
        assert not val.raw_text.startswith("\ufeff")

    def test_invalid_utf8_bytes_rejected(self) -> None:
        """Verify invalid non-UTF-8 bytes raise INVALID_ENCODING."""
        # \xff\xfe is UTF-16 LE marker or invalid UTF-8 sequence
        invalid_bytes = b"\xff\xfe\x00\x00Invalid bytes"
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_file_bytes(invalid_bytes)
        assert exc_info.value.code == "INVALID_ENCODING"

    def test_non_bytes_rejected_by_file_validator(self) -> None:
        """Verify non-bytes passed to file validator raises INVALID_INPUT_TYPE."""
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_file_bytes("string is not bytes")  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_INPUT_TYPE"

    def test_empty_file_bytes_rejected(self) -> None:
        """Verify empty file byte payload raises EMPTY_LOG_INPUT."""
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_file_bytes(b"")
        assert exc_info.value.code == "EMPTY_LOG_INPUT"

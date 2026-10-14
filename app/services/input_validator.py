"""Input validation service for LogLens AI.

Enforces configurable UTF-8 byte limits, line counts, individual line length limits,
strict type checking, and encoding validity before parsing is invoked.
"""

from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import InputValidationError
from app.models.validation_result import ValidatedLogInput
from app.utils.line_references import split_source_lines


def validate_log_input(
    log_text: Any, settings: Settings | None = None
) -> ValidatedLogInput:
    """Validate raw log text against security, size, line count, and encoding constraints.

    Args:
        log_text: The incoming log text to validate. Must be a string.
        settings: Application settings with limits. Defaults to get_settings().

    Returns:
        ValidatedLogInput with verified payload, byte size, and line count.

    Raises:
        InputValidationError: If any constraint is violated.
    """
    cfg = settings or get_settings()

    # 1. Type validation
    if not isinstance(log_text, str):
        raise InputValidationError(
            code="INVALID_INPUT_TYPE",
            message=f"Expected string input, received {type(log_text).__name__}.",
        )

    # 2. Empty and whitespace-only rejection
    if not log_text or not log_text.strip():
        raise InputValidationError(
            code="EMPTY_LOG_INPUT",
            message="The submitted log input is empty or contains only whitespace.",
        )

    # 3. UTF-8 byte encoding and size enforcement
    try:
        encoded = log_text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise InputValidationError(
            code="INVALID_ENCODING",
            message=f"Log content contains invalid Unicode characters: {exc.reason}.",
        ) from exc

    byte_size = len(encoded)
    if byte_size > cfg.MAX_LOG_SIZE_BYTES:
        raise InputValidationError(
            code="LOG_TOO_LARGE",
            message=(
                f"Log input size ({byte_size} bytes) exceeds the maximum allowed "
                f"limit of {cfg.MAX_LOG_SIZE_BYTES} bytes."
            ),
            limit=cfg.MAX_LOG_SIZE_BYTES,
            actual=byte_size,
        )

    # 4. Canonical line splitting and line count limit
    lines = split_source_lines(log_text)
    line_count = len(lines)
    if line_count > cfg.MAX_LOG_LINES:
        raise InputValidationError(
            code="TOO_MANY_LOG_LINES",
            message=(
                f"Log line count ({line_count}) exceeds the maximum allowed "
                f"limit of {cfg.MAX_LOG_LINES} lines."
            ),
            limit=cfg.MAX_LOG_LINES,
            actual=line_count,
        )

    # 5. Individual line length limit
    for idx, line in enumerate(lines, start=1):
        line_len = len(line)
        if line_len > cfg.MAX_LOG_LINE_LENGTH:
            raise InputValidationError(
                code="LOG_LINE_TOO_LONG",
                message=(
                    f"Line {idx} exceeds maximum allowed character length "
                    f"({cfg.MAX_LOG_LINE_LENGTH} characters)."
                ),
                line_number=idx,
                limit=cfg.MAX_LOG_LINE_LENGTH,
                actual=line_len,
            )

    return ValidatedLogInput(
        raw_text=log_text,
        byte_size=byte_size,
        line_count=line_count,
        is_valid=True,
    )


def validate_log_file_bytes(
    data: Any, settings: Settings | None = None
) -> ValidatedLogInput:
    """Validate uploaded raw file bytes, checking UTF-8 encoding and delegating to validate_log_input.

    Args:
        data: The raw uploaded bytes.
        settings: Application settings with limits. Defaults to get_settings().

    Returns:
        ValidatedLogInput with verified payload.

    Raises:
        InputValidationError: If data is not bytes, is invalid UTF-8, or violates limits.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise InputValidationError(
            code="INVALID_INPUT_TYPE",
            message=f"Expected bytes input, received {type(data).__name__}.",
        )

    if not data or not data.strip():
        raise InputValidationError(
            code="EMPTY_LOG_INPUT",
            message="The uploaded log file is empty or contains only whitespace.",
        )

    try:
        # utf-8-sig transparently handles and strips UTF-8 BOM if present
        decoded_text = data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise InputValidationError(
            code="INVALID_ENCODING",
            message=f"Uploaded file contains invalid UTF-8 byte sequences: {exc.reason}.",
        ) from exc

    return validate_log_input(decoded_text, settings=settings)


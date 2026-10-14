"""Domain exceptions for LogLens AI."""


class LogLensError(Exception):
    """Base exception for all LogLens AI domain errors."""


class LogParsingError(LogLensError):
    """Raised when an unrecoverable error occurs during log parsing."""


class InvalidLineReferenceError(LogLensError):
    """Raised when a line number or reference range is invalid or out of bounds."""


class InputValidationError(LogLensError):
    """Raised when incoming log input fails validation (size, type, lines, length, encoding)."""

    def __init__(
        self,
        code: str,
        message: str,
        line_number: int | None = None,
        limit: int | None = None,
        actual: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line_number = line_number
        self.limit = limit
        self.actual = actual


class EvidenceIntegrityError(LogLensError):
    """Raised when parsing or grouping evidence fails integrity validation."""

    def __init__(
        self,
        code: str,
        message: str,
        entity_id: str | None = None,
        line_number: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.entity_id = entity_id
        self.line_number = line_number

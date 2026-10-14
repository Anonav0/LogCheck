"""Domain exceptions for LogLens AI."""


class LogLensError(Exception):
    """Base exception for all LogLens AI domain errors."""


class LogParsingError(LogLensError):
    """Raised when an unrecoverable error occurs during log parsing."""


class InvalidLineReferenceError(LogLensError):
    """Raised when a line number or reference range is invalid or out of bounds."""


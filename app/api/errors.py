"""Centralized exception handlers and error mapping for LogLens AI REST API."""

import logging

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas.responses import ErrorDetail, ErrorResponse
from app.core.exceptions import EvidenceIntegrityError, InputValidationError

logger = logging.getLogger("loglens.api")


def _get_request_id(request: Request) -> str | None:
    """Retrieve the correlated request ID from request state or header."""
    return getattr(request.state, "request_id", None) or request.headers.get(
        "X-Request-ID"
    )


async def input_validation_error_handler(
    request: Request, exc: InputValidationError
) -> JSONResponse:
    """Handle domain InputValidationError, mapping to 413 or 422 based on the violation."""
    request_id = _get_request_id(request)

    # 413 Content Too Large for payload/line limits, 422 for format/empty errors
    if exc.code in ("LOG_TOO_LARGE", "TOO_MANY_LOG_LINES", "LOG_LINE_TOO_LONG"):
        status_code = status.HTTP_413_CONTENT_TOO_LARGE
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    logger.warning(
        "Input validation failed [%s] on %s: %s (request_id=%s)",
        exc.code,
        request.url.path,
        exc.message,
        request_id,
    )

    detail = ErrorDetail(
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        line_number=exc.line_number,
        limit=exc.limit,
        actual=exc.actual,
    )
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=detail).model_dump(exclude_none=True),
    )


async def evidence_integrity_error_handler(
    request: Request, exc: EvidenceIntegrityError
) -> JSONResponse:
    """Handle internal EvidenceIntegrityError as a safe 500 error."""
    request_id = _get_request_id(request)
    logger.error(
        "Evidence integrity verification failed [%s] on %s: %s (request_id=%s)",
        exc.code,
        request.url.path,
        exc.message,
        request_id,
    )

    detail = ErrorDetail(
        code="EVIDENCE_INTEGRITY_VIOLATION",
        message="Internal analysis evidence integrity verification failed.",
        request_id=request_id,
        line_number=exc.line_number,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(error=detail).model_dump(exclude_none=True),
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI/Pydantic request payload validation errors."""
    request_id = _get_request_id(request)
    errors = exc.errors()

    # Detect malformed JSON body
    is_json_decode_error = any(
        err.get("type") in ("json_invalid", "value_error.jsondecode")
        or "JSON decode error" in str(err.get("msg", ""))
        for err in errors
    )

    if is_json_decode_error:
        status_code = status.HTTP_400_BAD_REQUEST
        error_code = "MALFORMED_JSON"
        message = "The submitted request body is not valid JSON."
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        error_code = "VALIDATION_ERROR"
        # Provide clean, sanitized description of the primary validation failure
        first_err = errors[0] if errors else {}
        field = ".".join(str(loc) for loc in first_err.get("loc", []) if loc != "body")
        msg = first_err.get("msg", "Invalid request parameter.")
        message = f"Field '{field}': {msg}" if field else msg

    logger.warning(
        "Request validation error [%s] on %s: %s (request_id=%s)",
        error_code,
        request.url.path,
        message,
        request_id,
    )

    detail = ErrorDetail(
        code=error_code,
        message=message,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=detail).model_dump(exclude_none=True),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle standard FastAPI HTTPExceptions."""
    request_id = _get_request_id(request)

    code_map = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_413_CONTENT_TOO_LARGE: "PAYLOAD_TOO_LARGE",
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "UNPROCESSABLE_ENTITY",
        status.HTTP_429_TOO_MANY_REQUESTS: "TOO_MANY_REQUESTS",
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    }
    error_code = code_map.get(exc.status_code, "HTTP_ERROR")

    detail = ErrorDetail(
        code=error_code,
        message=str(exc.detail),
        request_id=request_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=detail).model_dump(exclude_none=True),
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled internal exceptions, returning safe 500 responses."""
    request_id = _get_request_id(request)
    logger.exception(
        "Unhandled internal exception on %s (request_id=%s)",
        request.url.path,
        request_id,
    )

    detail = ErrorDetail(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred while processing the request.",
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(error=detail).model_dump(exclude_none=True),
    )

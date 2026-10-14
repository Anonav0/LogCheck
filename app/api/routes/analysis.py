"""Log analysis endpoint routes."""

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_app_settings
from app.api.schemas.requests import AnalyzeLogRequest
from app.api.schemas.responses import (
    AnalysisStatus,
    AnalyzeLogResponse,
    ErrorResponse,
)
from app.core.config import Settings
from app.core.exceptions import EvidenceIntegrityError
from app.services.evidence_validator import (
    validate_analysis_result,
    validate_parsing_result,
)
from app.services.grouping import analyze_failures
from app.services.input_validator import validate_log_input
from app.services.llm import (
    analyze_failures_with_ai,
    build_deterministic_fallback,
)
from app.services.log_parser import parse_log_text

router = APIRouter(prefix="/api/v1", tags=["Analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeLogResponse,
    summary="Analyze Log Payload",
    description=(
        "Performs complete deterministic failure analysis on the submitted log text. "
        "Extracts structured entries, isolates failure events, groups recurring issues via "
        "SHA-256 fingerprinting, computes aggregate metrics, and optionally provides "
        "AI-assisted triage with strictly verified source-line evidence citations."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Malformed JSON payload"},
        413: {
            "model": ErrorResponse,
            "description": "Log size, line count, or line length exceeds limit",
        },
        422: {
            "model": ErrorResponse,
            "description": "Unprocessable entity or invalid input schema",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error or evidence integrity failure",
        },
    },
)
async def analyze_log(
    payload: AnalyzeLogRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AnalyzeLogResponse:
    """Execute end-to-end log analysis pipeline."""
    start_time = time.perf_counter()
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())

    # 1. Validate log text against size, line, and encoding limits
    validated_input = validate_log_input(payload.log_text, settings=settings)

    # 2. Parse log entries, failure events, and stack traces
    parsing_result = parse_log_text(validated_input.raw_text)

    # 3. Validate parsing evidence integrity
    parse_val = validate_parsing_result(validated_input.raw_text, parsing_result)
    if not parse_val.is_valid:
        first_err = parse_val.errors[0]
        raise EvidenceIntegrityError(
            code=first_err.code,
            message=first_err.message,
            entity_id=first_err.entity_id,
            line_number=first_err.line_number,
        )

    # 4. Fingerprint and group recurring failures
    failure_analysis = analyze_failures(parsing_result)

    # 5. Validate grouping and metrics evidence integrity
    group_val = validate_analysis_result(validated_input.raw_text, failure_analysis)
    if not group_val.is_valid:
        first_err = group_val.errors[0]
        raise EvidenceIntegrityError(
            code=first_err.code,
            message=first_err.message,
            entity_id=first_err.entity_id,
            line_number=first_err.line_number,
        )

    # 6. Optional AI-assisted triage
    ai_analysis = None
    analysis_source: str = "none"

    if payload.include_ai:
        if settings.LLM_ENABLED:
            ai_result = analyze_failures_with_ai(
                analysis_result=failure_analysis,
                raw_log=validated_input.raw_text,
                settings=settings,
            )
            ai_analysis = ai_result.analysis
            analysis_source = ai_result.analysis_source
        else:
            fallback_res = build_deterministic_fallback(
                analysis=failure_analysis,
                raw_log=validated_input.raw_text,
                fallback_reason="LLM_DISABLED",
            )
            ai_analysis = fallback_res.analysis
            analysis_source = "fallback"

    # 7. Determine overall analysis status
    if analysis_source == "fallback":
        analysis_status = AnalysisStatus.COMPLETED_WITH_FALLBACK
    elif parsing_result.parser_warnings:
        analysis_status = AnalysisStatus.COMPLETED_WITH_WARNINGS
    else:
        analysis_status = AnalysisStatus.COMPLETED

    elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

    return AnalyzeLogResponse(
        request_id=request_id,
        status=analysis_status,
        metrics=failure_analysis.metrics,
        parsed_entries=parsing_result.entries,
        failure_events=parsing_result.failure_events,
        failure_groups=failure_analysis.failure_groups,
        parser_warnings=parsing_result.parser_warnings,
        ai_analysis=ai_analysis,
        analysis_source=analysis_source,  # type: ignore[arg-type]
        processing_time_ms=elapsed_ms,
    )

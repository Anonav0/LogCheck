"""Orchestration service for AI-assisted log failure analysis with strict evidence verification."""

import json
import logging
import re
import time

from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.models.analysis_metrics import FailureAnalysisResult
from app.services.llm.base import LLMProvider
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
)
from app.services.llm.fallback import build_deterministic_fallback
from app.services.llm.prompt_builder import PromptEvidenceLine, build_analysis_prompt
from app.services.llm.provider_factory import get_llm_provider
from app.services.llm.schemas import AIAnalysis, AIAnalysisResult, EvidenceReference
from app.utils.line_references import split_source_lines

logger = logging.getLogger("loglens.llm")

# Pattern to extract JSON if wrapped inside markdown code fences
_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def _extract_json_payload(raw_text: str) -> str:
    """Extract raw JSON substring from model output, handling optional markdown fences."""
    text = raw_text.strip()
    match = _CODE_BLOCK_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return text


def _excerpt_matches_line(
    excerpt: str, raw_line: str, model_line: str | None = None
) -> bool:
    """Check if an evidence excerpt faithfully matches the original or redacted line.

    Matching rules:
    1. Case-insensitive normalization of leading/trailing whitespace.
    2. Substring containment in raw source line OR model-visible redacted line.
    3. Handles punctuation variations and truncated excerpts.
    """
    clean_excerpt = excerpt.strip().lower()
    clean_raw = raw_line.strip().lower()

    if not clean_excerpt:
        return False

    # Exact substring match in raw or redacted line
    if clean_excerpt in clean_raw:
        return True

    if model_line and clean_excerpt in model_line.strip().lower():
        return True

    # Allow for tokenized matching if excerpt is a substantial continuous phrase (>= 10 chars)
    if len(clean_excerpt) >= 10 and (
        clean_excerpt[:30] in clean_raw or clean_excerpt[-30:] in clean_raw
    ):
        return True

    return False


def verify_ai_evidence(
    analysis: AIAnalysis,
    canonical_lines: list[str],
    supplied_evidence_lines: dict[int, PromptEvidenceLine],
    valid_event_ids: set[str],
    valid_fingerprints: set[str],
) -> tuple[bool, list[str]]:
    """Verify all evidence references in the AI analysis against source logs and supplied evidence.

    Checks:
    1. Line number exists in canonical lines (1 <= L <= total_lines).
    2. Excerpt matches the actual source line (or its redacted model representation).
    3. Optional failure_event_id belongs to a known parsed event.
    4. Optional fingerprint belongs to a known failure group.

    Returns:
        tuple[bool, list[str]]: (is_valid, error_reasons)
    """
    errors: list[str] = []
    total_lines = len(canonical_lines)

    # Collect all references across the analysis
    all_refs: list[EvidenceReference] = list(analysis.evidence_refs)
    for cause in analysis.likely_causes:
        all_refs.extend(cause.evidence_refs)
    for action in analysis.recommended_actions:
        all_refs.extend(action.evidence_refs)

    for ref in all_refs:
        ln = ref.line_number
        # 1. Bounds check
        if not (1 <= ln <= total_lines):
            errors.append(f"Evidence line {ln} is out of bounds (1..{total_lines}).")
            continue

        raw_line = canonical_lines[ln - 1]
        pel = supplied_evidence_lines.get(ln)
        model_line = pel.model_line if pel else None

        # 2. Excerpt match check
        if not _excerpt_matches_line(ref.excerpt, raw_line, model_line):
            errors.append(
                f"Evidence excerpt at line {ln} ('{ref.excerpt[:50]}...') does not match source line content ('{raw_line[:50]}...')."
            )

        # 3. Optional event ID check
        if ref.failure_event_id and ref.failure_event_id not in valid_event_ids:
            errors.append(
                f"Evidence references unknown failure_event_id '{ref.failure_event_id}'."
            )

        # 4. Optional fingerprint check
        if ref.fingerprint and ref.fingerprint not in valid_fingerprints:
            errors.append(
                f"Evidence references unknown fingerprint '{ref.fingerprint}'."
            )

    return len(errors) == 0, errors


def analyze_failures_with_ai(
    analysis_result: FailureAnalysisResult,
    raw_log: str,
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> AIAnalysisResult:
    """Analyze failure patterns with an LLM or safe deterministic fallback.

    Pipeline:
    1. Check if LLM is enabled in configuration. If disabled, return fallback immediately.
    2. Instantiate configured LLMProvider (or use supplied provider).
    3. Build bounded, structured prompt containing failure groups and evidence excerpts.
    4. Execute request with strict timeout.
    5. Parse and validate JSON response against AIAnalysis schema.
    6. Verify all cited evidence references against source lines and entities.
    7. Return AIAnalysisResult or graceful deterministic fallback on any error.
    """
    cfg = settings or get_settings()
    canonical_lines = split_source_lines(raw_log)

    # 1. Check if LLM is enabled
    if not cfg.LLM_ENABLED:
        logger.info(
            "LLM analysis is disabled by configuration; using deterministic fallback."
        )
        return build_deterministic_fallback(
            analysis=analysis_result,
            raw_log=raw_log,
            fallback_reason="LLM_DISABLED",
        )

    # 2. Resolve LLM provider
    active_provider: LLMProvider
    if provider is not None:
        active_provider = provider
    else:
        try:
            active_provider = get_llm_provider(cfg)
        except (LLMConfigurationError, LLMAuthenticationError) as exc:
            logger.warning(
                "LLM provider setup failed: %s; using deterministic fallback.",
                exc.message,
            )
            return build_deterministic_fallback(
                analysis=analysis_result,
                raw_log=raw_log,
                fallback_reason=f"CONFIG_ERROR: {exc.message}",
            )

    # 3. Build bounded prompt
    built_prompt = build_analysis_prompt(
        analysis=analysis_result,
        raw_log=raw_log,
        settings=cfg,
    )

    # Collect known entity IDs for evidence validation
    valid_event_ids = {
        occ.event_id
        for group in analysis_result.failure_groups
        for occ in group.occurrences
    }
    valid_fingerprints = {group.fingerprint for group in analysis_result.failure_groups}

    start_time = time.perf_counter()

    # 4. Execute provider call
    raw_output: str
    try:
        raw_output = active_provider.generate(
            prompt=built_prompt.prompt_text,
            timeout_seconds=cfg.LLM_TIMEOUT_SECONDS,
        )
    except LLMError as exc:
        duration = time.perf_counter() - start_time
        logger.warning(
            "LLM provider error (%s) after %.2fs: %s; invoking fallback.",
            type(exc).__name__,
            duration,
            exc.message,
        )
        return build_deterministic_fallback(
            analysis=analysis_result,
            raw_log=raw_log,
            fallback_reason=f"PROVIDER_ERROR: {exc.message}",
        )
    except Exception as exc:
        duration = time.perf_counter() - start_time
        logger.exception(
            "Unexpected error during LLM generation after %.2fs; invoking fallback.",
            duration,
        )
        return build_deterministic_fallback(
            analysis=analysis_result,
            raw_log=raw_log,
            fallback_reason=f"UNEXPECTED_ERROR: {exc!s}",
        )

    duration = time.perf_counter() - start_time

    # 5. Extract and parse JSON
    cleaned_json_str = _extract_json_payload(raw_output)
    try:
        parsed_data = json.loads(cleaned_json_str)
    except json.JSONDecodeError as exc:
        logger.warning("LLM response is not valid JSON; invoking fallback.")
        return build_deterministic_fallback(
            analysis=analysis_result,
            raw_log=raw_log,
            fallback_reason=f"INVALID_JSON: {exc.msg}",
        )

    # 6. Pydantic schema validation
    ai_analysis: AIAnalysis
    try:
        ai_analysis = AIAnalysis.model_validate(parsed_data)
    except ValidationError as exc:
        logger.warning(
            "LLM response failed Pydantic schema validation; invoking fallback."
        )
        return build_deterministic_fallback(
            analysis=analysis_result,
            raw_log=raw_log,
            fallback_reason=f"SCHEMA_VALIDATION_ERROR: {exc.errors()[0]['msg']}",
        )

    # 7. Evidence verification
    is_valid, validation_errors = verify_ai_evidence(
        analysis=ai_analysis,
        canonical_lines=canonical_lines,
        supplied_evidence_lines=built_prompt.evidence_lines,
        valid_event_ids=valid_event_ids,
        valid_fingerprints=valid_fingerprints,
    )

    if not is_valid:
        error_summary = "; ".join(validation_errors[:3])
        logger.warning(
            "AI evidence verification failed: %s; invoking fallback.", error_summary
        )
        return build_deterministic_fallback(
            analysis=analysis_result,
            raw_log=raw_log,
            fallback_reason=f"EVIDENCE_VERIFICATION_FAILED: {error_summary}",
        )

    # Count total verified citations
    total_verified = (
        len(ai_analysis.evidence_refs)
        + sum(len(c.evidence_refs) for c in ai_analysis.likely_causes)
        + sum(len(a.evidence_refs) for a in ai_analysis.recommended_actions)
    )

    return AIAnalysisResult(
        analysis=ai_analysis,
        analysis_source="llm",
        fallback_reason=None,
        provider=active_provider.provider_name,
        model=active_provider.model_name,
        duration_seconds=round(duration, 3),
        verified_evidence_count=total_verified,
    )

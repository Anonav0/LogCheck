"""Deterministic fallback analysis service for LogLens AI.

Generates a fully structured, verified AIAnalysis result derived exclusively
from deterministic parsing, fingerprinting, and grouping metrics without relying
on external LLM access.
"""

from app.models.analysis_metrics import FailureAnalysisResult
from app.models.failure_event import FailureEventType
from app.services.llm.schemas import (
    AIAnalysis,
    AIAnalysisResult,
    EvidenceReference,
    LikelyCause,
    RecommendedAction,
)
from app.utils.line_references import split_source_lines


def _generate_generic_actions_for_type(
    failure_type: FailureEventType,
    first_seen_line: int,
    raw_excerpt: str,
    event_id: str | None,
    fingerprint: str | None,
) -> list[RecommendedAction]:
    """Generate pragmatic, deterministic investigation actions based on detected failure category."""
    ref = EvidenceReference(
        line_number=first_seen_line,
        excerpt=raw_excerpt[:200] if raw_excerpt else f"Line {first_seen_line}",
        failure_event_id=event_id,
        fingerprint=fingerprint,
    )

    if failure_type == FailureEventType.EXCEPTION:
        return [
            RecommendedAction(
                action=f"Inspect the traceback frames culminating at line {first_seen_line} for unhandled exceptions or state invariants.",
                rationale="Tracebacks pinpoint the immediate call site, nested cause chain, and error condition.",
                priority="high",
                evidence_refs=[ref],
            ),
            RecommendedAction(
                action="Verify input parameters, external connection pools, and error preconditions.",
                rationale="Exceptions typically stem from unexpected payload structures, timeouts, or backend saturation.",
                priority="medium",
                evidence_refs=[ref],
            ),
        ]

    if failure_type == FailureEventType.ASSERTION_FAILURE:
        return [
            RecommendedAction(
                action=f"Review test expectations and assertion operands evaluated at line {first_seen_line}.",
                rationale="Assertion failures indicate a mismatch between expected test contract and actual runtime state.",
                priority="high",
                evidence_refs=[ref],
            )
        ]

    if failure_type == FailureEventType.TEST_FAILURE:
        return [
            RecommendedAction(
                action=f"Investigate test suite runner failure status reported at line {first_seen_line}.",
                rationale="Runner failures indicate either assertion violations or unexpected test execution aborts.",
                priority="high",
                evidence_refs=[ref],
            )
        ]

    # Explicit ERROR / CRITICAL message fallback
    return [
        RecommendedAction(
            action=f"Review component configuration and operational logs around line {first_seen_line}.",
            rationale="Deterministic error entries indicate subsystem errors or operational threshold alerts.",
            priority="medium",
            evidence_refs=[ref],
        )
    ]


def build_deterministic_fallback(
    analysis: FailureAnalysisResult,
    raw_log: str,
    fallback_reason: str,
) -> AIAnalysisResult:
    """Generate a valid, deterministic AIAnalysisResult from existing analysis metrics.

    Args:
        analysis: Deterministic parsing, fingerprinting, and grouping results.
        raw_log: Original raw log text (used to retrieve exact source excerpts).
        fallback_reason: Technical explanation of why fallback was invoked.

    Returns:
        AIAnalysisResult: Validated analysis container with analysis_source="fallback".
    """
    source_lines = split_source_lines(raw_log)
    total_lines = len(source_lines)

    total_events = analysis.metrics.total_failure_events
    unique_groups = analysis.metrics.unique_failure_groups
    groups = analysis.failure_groups

    # Build executive summary
    if total_events == 0:
        summary = (
            f"Deterministic log analysis completed across {total_lines} source lines. "
            f"No error events, exceptions, or test failures were detected in the log payload."
        )
        confidence = 1.0
        likely_causes: list[LikelyCause] = []
        recommended_actions: list[RecommendedAction] = [
            RecommendedAction(
                action="Continue routine monitoring of service health and metrics.",
                rationale="No actionable failures or stack traces were detected in the provided log stream.",
                priority="low",
                evidence_refs=[],
            )
        ]
        all_evidence_refs: list[EvidenceReference] = []

    else:
        most_frequent = groups[0] if groups else None
        freq_desc = (
            f" Most frequent failure is '{most_frequent.title}' with {most_frequent.occurrence_count} occurrences."
            if most_frequent
            else ""
        )
        summary = (
            f"Deterministic failure analysis identified {total_events} failure event(s) "
            f"clustered into {unique_groups} distinct failure group(s) across {total_lines} lines.{freq_desc}"
        )
        confidence = (
            0.5  # Deterministic heuristics express explicit uncertainty without LLM
        )

        likely_causes = []
        recommended_actions = []
        all_evidence_refs = []

        # Generate causes and actions from the top failure groups (up to 5)
        for group in groups[:5]:
            sample_occ = group.occurrences[0] if group.occurrences else None
            first_line = group.first_seen_line

            # Fetch exact source line excerpt
            if 1 <= first_line <= total_lines:
                excerpt = source_lines[first_line - 1].strip()
            else:
                excerpt = group.representative_message

            ref = EvidenceReference(
                line_number=first_line,
                excerpt=excerpt[:200] if excerpt else f"Line {first_line}",
                failure_event_id=sample_occ.event_id if sample_occ else None,
                fingerprint=group.fingerprint,
            )
            all_evidence_refs.append(ref)

            cause_desc = f"{group.title} (detected {group.occurrence_count} time(s))"
            reasoning = (
                f"Deterministic grouping matched {group.occurrence_count} event(s) sharing fingerprint "
                f"{group.fingerprint[:16]}... first seen at line {group.first_seen_line} and last seen "
                f"at line {group.last_seen_line}."
            )
            likely_causes.append(
                LikelyCause(
                    description=cause_desc,
                    reasoning=reasoning,
                    evidence_refs=[ref],
                )
            )

            # Add category-specific actions
            actions = _generate_generic_actions_for_type(
                failure_type=group.failure_category,
                first_seen_line=first_line,
                raw_excerpt=excerpt,
                event_id=sample_occ.event_id if sample_occ else None,
                fingerprint=group.fingerprint,
            )
            recommended_actions.extend(actions)

    limitations = [
        f"Analysis generated by deterministic rule-based engine due to: {fallback_reason}.",
        "Hypotheses reflect static exception patterns and line references without generative LLM reasoning.",
        "External infrastructure telemetry and code repository context were not accessible during analysis.",
    ]

    analysis_payload = AIAnalysis(
        summary=summary,
        likely_causes=likely_causes,
        recommended_actions=recommended_actions,
        confidence=confidence,
        limitations=limitations,
        evidence_refs=all_evidence_refs,
    )

    return AIAnalysisResult(
        analysis=analysis_payload,
        analysis_source="fallback",
        fallback_reason=fallback_reason,
        provider="deterministic_fallback",
        model=None,
        duration_seconds=0.0,
        verified_evidence_count=len(all_evidence_refs),
    )

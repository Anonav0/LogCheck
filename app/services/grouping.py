"""Deterministic grouping of failure events by fingerprint and metrics calculation."""

from collections import defaultdict

from app.models.analysis_metrics import AnalysisMetrics, FailureAnalysisResult
from app.models.failure_event import FailureEvent
from app.models.failure_group import FailureGroup, FailureOccurrence
from app.models.log_entry import LogLevel
from app.models.parsing_result import ParsingResult
from app.services.fingerprinting import (
    extract_failure_signature,
    generate_fingerprint,
)


def _derive_group_title(event: FailureEvent, normalized_msg: str) -> str:
    """Derive a concise, human-readable title for a failure group."""
    if event.exception_type:
        if normalized_msg and normalized_msg != event.exception_type:
            # Shorten very long messages in title if needed
            msg_snippet = (
                normalized_msg[:80] + "..."
                if len(normalized_msg) > 80
                else normalized_msg
            )
            return f"{event.exception_type}: {msg_snippet}"
        return event.exception_type

    if normalized_msg:
        return (
            normalized_msg[:90] + "..." if len(normalized_msg) > 90 else normalized_msg
        )

    return f"Failure Event ({event.event_type.value})"


def _aggregate_severity(occurrences: list[FailureOccurrence]) -> LogLevel | None:
    """Aggregate severity across occurrences using standard precedence."""
    levels = [occ.level for occ in occurrences if occ.level is not None]
    if not levels:
        return None
    if LogLevel.CRITICAL in levels:
        return LogLevel.CRITICAL
    if LogLevel.ERROR in levels:
        return LogLevel.ERROR
    if LogLevel.WARNING in levels:
        return LogLevel.WARNING
    if LogLevel.INFO in levels:
        return LogLevel.INFO
    return levels[0]


def _aggregate_component(occurrences: list[FailureOccurrence]) -> str | None:
    """Determine common component if consistent, else return None for mixed."""
    components = {occ.logger_name for occ in occurrences if occ.logger_name is not None}
    if len(components) == 1:
        return next(iter(components))
    return None


def group_failures(events: list[FailureEvent]) -> list[FailureGroup]:
    """Group a collection of FailureEvents deterministically by their stable fingerprint.

    Sorting Rules for Groups:
        1. occurrence_count (descending)
        2. first_seen_line (ascending)
        3. fingerprint (ascending lexicographical tie-breaker)

    Sorting Rules for Occurrences within each Group:
        1. primary_line_number (ascending)
        2. event_id (ascending lexicographical tie-breaker)
    """
    if not events:
        return []

    # Map fingerprint to list of (event, occurrence)
    grouped_occurrences: dict[str, list[FailureOccurrence]] = defaultdict(list)
    group_prototypes: dict[str, FailureEvent] = {}

    for event in events:
        fp = generate_fingerprint(event)
        occurrence = FailureOccurrence(
            event_id=event.event_id,
            primary_line_number=event.primary_line_number,
            start_line_number=event.start_line_number,
            end_line_number=event.end_line_number,
            line_numbers=list(event.line_numbers),
            original_message=event.message,
            exception_type=event.exception_type,
            timestamp=event.timestamp,
            level=event.level,
            logger_name=event.logger_name,
        )
        grouped_occurrences[fp].append(occurrence)
        if fp not in group_prototypes:
            group_prototypes[fp] = event

    groups: list[FailureGroup] = []

    for fp, occurrences in grouped_occurrences.items():
        proto_event = group_prototypes[fp]
        sig = extract_failure_signature(proto_event)

        # Sort occurrences deterministically
        sorted_occurrences = sorted(
            occurrences,
            key=lambda occ: (occ.primary_line_number, occ.event_id),
        )

        # Combine all unique line numbers sorted
        all_lines: set[int] = set()
        for occ in sorted_occurrences:
            all_lines.update(occ.line_numbers)
        sorted_lines = sorted(all_lines)

        first_seen = min(occ.primary_line_number for occ in sorted_occurrences)
        last_seen = max(occ.primary_line_number for occ in sorted_occurrences)

        title = _derive_group_title(proto_event, sig.normalized_message)
        severity = _aggregate_severity(sorted_occurrences)
        component = _aggregate_component(sorted_occurrences)

        group = FailureGroup(
            fingerprint=fp,
            title=title,
            failure_category=proto_event.event_type,
            exception_type=proto_event.exception_type,
            representative_message=sig.normalized_message,
            occurrence_count=len(sorted_occurrences),
            occurrences=sorted_occurrences,
            line_numbers=sorted_lines,
            first_seen_line=first_seen,
            last_seen_line=last_seen,
            severity=severity,
            component=component,
        )
        groups.append(group)

    # Sort groups deterministically:
    # 1. occurrence_count DESC
    # 2. first_seen_line ASC
    # 3. fingerprint ASC
    groups.sort(key=lambda g: (-g.occurrence_count, g.first_seen_line, g.fingerprint))

    return groups


def compute_analysis_metrics(
    total_log_lines: int,
    total_error_entries: int,
    total_warning_entries: int,
    groups: list[FailureGroup],
) -> AnalysisMetrics:
    """Calculate deterministic summary and recurrence metrics from failure groups."""
    total_failure_events = sum(g.occurrence_count for g in groups)
    unique_groups = len(groups)
    repeated_groups = sum(1 for g in groups if g.occurrence_count > 1)
    repeated_events = sum(g.occurrence_count for g in groups if g.occurrence_count > 1)
    most_frequent = max((g.occurrence_count for g in groups), default=0)

    return AnalysisMetrics(
        total_log_lines=total_log_lines,
        total_error_entries=total_error_entries,
        total_warning_entries=total_warning_entries,
        total_failure_events=total_failure_events,
        unique_failure_groups=unique_groups,
        repeated_failure_groups=repeated_groups,
        repeated_failure_events=repeated_events,
        most_frequent_failure_count=most_frequent,
    )


def analyze_failures(parsing_result: ParsingResult) -> FailureAnalysisResult:
    """Analyze and group failure events from a ParsingResult and compute aggregate metrics."""
    groups = group_failures(parsing_result.failure_events)
    metrics = compute_analysis_metrics(
        total_log_lines=parsing_result.total_lines,
        total_error_entries=parsing_result.error_count,
        total_warning_entries=parsing_result.warning_count,
        groups=groups,
    )
    return FailureAnalysisResult(
        parsing_result=parsing_result,
        failure_groups=groups,
        metrics=metrics,
    )

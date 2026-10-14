"""Deterministic log parser orchestrating line parsing, stack trace extraction, and event assembly."""

import json
import re

from app.models.failure_event import FailureEvent, FailureEventType
from app.models.log_entry import (
    LineCategory,
    LogLevel,
    ParsedLogEntry,
    normalize_log_level,
)
from app.models.parsing_result import ParsingResult
from app.services.exception_detector import (
    detect_assertion_failure,
    detect_java_exception,
    detect_python_exception,
)
from app.services.stack_trace_parser import (
    is_java_caused_by,
    is_java_stack_frame,
    is_java_suppressed,
    is_java_truncated_frame,
    is_python_chaining_marker,
    is_python_stack_frame,
    is_python_traceback_header,
)

# Common structured log line regex patterns
# 1. Standard timestamp + bracketed level + logger + message
# e.g.: 2026-10-14 08:30:01,102 [INFO] app.server: Starting LogLens
_LOG_PATTERN_BRACKET = re.compile(
    r"^(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,\.]\d{3,6})?(?:[+-]\d{2}:?\d{2}|Z)?)\s+\[([A-Za-z]+)\]\s+([^:]+):\s*(.*)$"
)

# 2. Timestamp + level + logger + delimiter + message
# e.g.: 2026-10-14 10:15:30 INFO application.worker - Job started
_LOG_PATTERN_SPACED = re.compile(
    r"^(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,\.]\d{3,6})?(?:[+-]\d{2}:?\d{2}|Z)?)\s+([A-Za-z]+)\s+([^\s\-:]+)\s*[-:]\s*(.*)$"
)

# 3. Bracketed level at start of line: [ERROR] PaymentService - Transaction failed
_LOG_PATTERN_BRACKET_START = re.compile(
    r"^\[([A-Za-z]+)\]\s+([^\s\-:]+)\s*[-:]\s*(.*)$"
)

# 4. Level prefix at start: ERROR: Unable to process request
_LOG_PATTERN_LEVEL_PREFIX = re.compile(r"^([A-Za-z]+):\s*(.*)$")

# 5. Bracketed timestamp with unusual alert: [2026/10/14-09:40:00] !!! UNUSUAL_ALERT !!! ...
_LOG_PATTERN_BRACKET_TS = re.compile(
    r"^\[(\d{4}[/-]\d{2}[/-]\d{2}[-T ]\d{2}:\d{2}:\d{2})\]\s+(.*)$"
)


class LogParser:
    """Orchestrates deterministic parsing of multiline application and test logs."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def parse(self, log_text: str) -> ParsingResult:
        """Parse raw multiline log text into a structured ParsingResult."""
        self.warnings = []

        if not log_text:
            return ParsingResult(total_lines=0)

        # 1. Split lines preserving exact source lines without line terminators
        raw_lines = log_text.splitlines()
        total_lines = len(raw_lines)

        # 2. Parse individual line metadata
        entries: list[ParsedLogEntry] = []
        for line_idx, raw_line in enumerate(raw_lines, start=1):
            entry = self._parse_line_metadata(line_idx, raw_line)
            entries.append(entry)

        # 3. Assemble failure events (tracebacks, exceptions, explicit errors, test failures)
        failure_events = self._assemble_failure_events(entries)

        # 4. Calculate summary metrics
        error_count = sum(
            1 for e in entries if e.level in (LogLevel.ERROR, LogLevel.CRITICAL)
        )
        warning_count = sum(1 for e in entries if e.level == LogLevel.WARNING)
        stack_trace_line_count = sum(
            1
            for e in entries
            if e.category
            in (
                LineCategory.STACK_FRAME,
                LineCategory.TRACEBACK_HEADER,
            )
            or (e.category == LineCategory.EXCEPTION and e.failure_event_id is not None)
        )

        return ParsingResult(
            total_lines=total_lines,
            entries=entries,
            failure_events=failure_events,
            error_count=error_count,
            warning_count=warning_count,
            failure_event_count=len(failure_events),
            stack_trace_line_count=stack_trace_line_count,
            parser_warnings=list(self.warnings),
        )

    def _parse_line_metadata(self, line_number: int, raw_line: str) -> ParsedLogEntry:
        """Parse an individual source line into a ParsedLogEntry with preliminary metadata."""
        stripped = raw_line.strip()

        # Handle empty lines
        if not stripped:
            return ParsedLogEntry(
                line_number=line_number,
                raw_line=raw_line,
                message="",
                category=LineCategory.UNKNOWN,
            )

        # Check for JSON-formatted line
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict):
                    raw_level = (
                        data.get("level")
                        or data.get("severity")
                        or data.get("log_level")
                    )
                    level = normalize_log_level(str(raw_level) if raw_level else None)
                    ts = data.get("timestamp") or data.get("time") or data.get("ts")
                    timestamp = str(ts) if ts is not None else None
                    logger = (
                        data.get("logger")
                        or data.get("logger_name")
                        or data.get("component")
                    )
                    logger_name = str(logger) if logger is not None else None
                    msg = data.get("message") or data.get("msg") or stripped

                    category = LineCategory.NORMAL
                    if level in (LogLevel.ERROR, LogLevel.CRITICAL):
                        category = LineCategory.ERROR
                    elif level == LogLevel.WARNING:
                        category = LineCategory.WARNING

                    return ParsedLogEntry(
                        line_number=line_number,
                        raw_line=raw_line,
                        timestamp=timestamp,
                        level=level,
                        logger_name=logger_name,
                        message=str(msg),
                        category=category,
                    )
            except (json.JSONDecodeError, ValueError):
                # Malformed JSON lines should not crash the parser
                pass

        # Check Standard Pattern 1: Timestamp + [LEVEL] + logger: message
        match1 = _LOG_PATTERN_BRACKET.match(raw_line)
        if match1:
            timestamp, raw_level, logger_name, message = match1.groups()
            level = normalize_log_level(raw_level)
            category = self._category_from_level(level)
            return ParsedLogEntry(
                line_number=line_number,
                raw_line=raw_line,
                timestamp=timestamp,
                level=level,
                logger_name=logger_name.strip(),
                message=message,
                category=category,
            )

        # Check Standard Pattern 2: Timestamp + LEVEL + logger - message
        match2 = _LOG_PATTERN_SPACED.match(raw_line)
        if match2:
            timestamp, raw_level, logger_name, message = match2.groups()
            level = normalize_log_level(raw_level)
            if level is not None:
                category = self._category_from_level(level)
                return ParsedLogEntry(
                    line_number=line_number,
                    raw_line=raw_line,
                    timestamp=timestamp,
                    level=level,
                    logger_name=logger_name.strip(),
                    message=message,
                    category=category,
                )

        # Check Pattern 3: [LEVEL] logger - message
        match3 = _LOG_PATTERN_BRACKET_START.match(raw_line)
        if match3:
            raw_level, logger_name, message = match3.groups()
            level = normalize_log_level(raw_level)
            if level is not None:
                category = self._category_from_level(level)
                return ParsedLogEntry(
                    line_number=line_number,
                    raw_line=raw_line,
                    level=level,
                    logger_name=logger_name.strip(),
                    message=message,
                    category=category,
                )

        # Check Pattern 4: LEVEL: message
        match4 = _LOG_PATTERN_LEVEL_PREFIX.match(raw_line)
        if match4:
            raw_level, message = match4.groups()
            level = normalize_log_level(raw_level)
            if level is not None:
                category = self._category_from_level(level)
                return ParsedLogEntry(
                    line_number=line_number,
                    raw_line=raw_line,
                    level=level,
                    message=message,
                    category=category,
                )

        # Check Pattern 5: Bracketed timestamp with unclassified content
        match5 = _LOG_PATTERN_BRACKET_TS.match(raw_line)
        if match5:
            timestamp, message = match5.groups()
            return ParsedLogEntry(
                line_number=line_number,
                raw_line=raw_line,
                timestamp=timestamp,
                message=message,
                category=LineCategory.UNKNOWN,
            )

        # Check for stack trace or exception patterns
        if is_python_traceback_header(raw_line):
            return ParsedLogEntry(
                line_number=line_number,
                raw_line=raw_line,
                message=stripped,
                category=LineCategory.TRACEBACK_HEADER,
            )

        if is_python_stack_frame(raw_line) or is_java_stack_frame(raw_line):
            return ParsedLogEntry(
                line_number=line_number,
                raw_line=raw_line,
                message=stripped,
                category=LineCategory.STACK_FRAME,
            )

        # Fallback for unrecognized line
        return ParsedLogEntry(
            line_number=line_number,
            raw_line=raw_line,
            message=raw_line,
            category=LineCategory.UNKNOWN,
        )

    def _category_from_level(self, level: LogLevel | None) -> LineCategory:
        """Derive default LineCategory from recognized LogLevel."""
        if level in (LogLevel.ERROR, LogLevel.CRITICAL):
            return LineCategory.ERROR
        if level == LogLevel.WARNING:
            return LineCategory.WARNING
        if level is not None:
            return LineCategory.NORMAL
        return LineCategory.UNKNOWN

    def _assemble_failure_events(
        self, entries: list[ParsedLogEntry]
    ) -> list[FailureEvent]:
        """Group parsed entries into discrete logical failure events."""
        events: list[FailureEvent] = []
        n = len(entries)
        i = 0
        event_counter = 1

        while i < n:
            entry = entries[i]

            # 1. Check for Python Traceback
            if is_python_traceback_header(entry.raw_line):
                # Check if preceding entry was an associated explicit error log
                preceding_error: ParsedLogEntry | None = None
                if i > 0 and entries[i - 1].level in (
                    LogLevel.ERROR,
                    LogLevel.CRITICAL,
                ):
                    preceding_error = entries[i - 1]

                event, next_idx = self._parse_python_traceback_event(
                    entries, i, event_counter, preceding_error
                )
                if event:
                    events.append(event)
                    event_counter += 1
                i = next_idx
                continue

            # 2. Check for Java Stack Trace (exception declaration followed by Java frames)
            java_exc = detect_java_exception(entry.raw_line)
            if java_exc and (
                i + 1 < n and is_java_stack_frame(entries[i + 1].raw_line)
            ):
                event, next_idx = self._parse_java_trace_event(
                    entries, i, event_counter, None
                )
                if event:
                    events.append(event)
                    event_counter += 1
                i = next_idx
                continue

            # 3. Check for Pytest test failure section: e.g. "____ test_name ____"
            if entry.raw_line.startswith("____") and entry.raw_line.endswith("____"):
                event, next_idx = self._parse_pytest_failure_event(
                    entries, i, event_counter
                )
                if event:
                    events.append(event)
                    event_counter += 1
                i = next_idx
                continue

            # 4. Check for standalone Pytest assertion failure: "E       AssertionError: ..."
            assertion_data = detect_assertion_failure(entry.raw_line)
            if (
                assertion_data
                and entry.failure_event_id is None
                and not entry.raw_line.startswith("FAILED")
            ):
                event, next_idx = self._parse_assertion_event(entries, i, event_counter)
                if event:
                    events.append(event)
                    event_counter += 1
                i = next_idx
                continue

            # 5. Check for Standalone Explicit ERROR / CRITICAL log line
            # Only if not already claimed by a preceding event or followed by traceback
            if (
                entry.level in (LogLevel.ERROR, LogLevel.CRITICAL)
                and entry.failure_event_id is None
            ):
                # If next line is a traceback header, let next iteration handle it with preceding_error
                if i + 1 < n and is_python_traceback_header(entries[i + 1].raw_line):
                    i += 1
                    continue

                event_id = f"event-{event_counter}"
                entry.failure_event_id = event_id
                event = FailureEvent(
                    event_id=event_id,
                    event_type=FailureEventType.EXPLICIT_ERROR,
                    exception_type=None,
                    message=entry.message,
                    primary_line_number=entry.line_number,
                    start_line_number=entry.line_number,
                    end_line_number=entry.line_number,
                    line_numbers=[entry.line_number],
                    stack_trace=[],
                    timestamp=entry.timestamp,
                    level=entry.level,
                    logger_name=entry.logger_name,
                )
                events.append(event)
                event_counter += 1

            i += 1

        return events

    def _parse_python_traceback_event(
        self,
        entries: list[ParsedLogEntry],
        header_idx: int,
        event_num: int,
        preceding_error: ParsedLogEntry | None,
    ) -> tuple[FailureEvent | None, int]:
        """Extract a complete Python traceback block and build a FailureEvent."""
        event_id = f"event-{event_num}"
        event_lines: list[ParsedLogEntry] = []

        if preceding_error:
            preceding_error.failure_event_id = event_id
            event_lines.append(preceding_error)

        curr = header_idx
        n = len(entries)
        header_entry = entries[curr]
        header_entry.category = LineCategory.TRACEBACK_HEADER
        header_entry.failure_event_id = event_id
        event_lines.append(header_entry)
        curr += 1

        terminal_entry: ParsedLogEntry | None = None
        exception_type: str | None = None
        exception_msg: str = ""

        while curr < n:
            e = entries[curr]
            raw = e.raw_line

            # Check if this line is another log entry with a timestamp/level (boundary stop)
            if e.level is not None and not is_python_traceback_header(raw):
                # Don't absorb unrelated subsequent log entries!
                break

            # Frame line
            if is_python_stack_frame(raw):
                e.category = LineCategory.STACK_FRAME
                e.failure_event_id = event_id
                event_lines.append(e)
                curr += 1
                # Consume indented code lines directly beneath this frame
                while (
                    curr < n
                    and entries[curr].raw_line.startswith(" ")
                    and not is_python_stack_frame(entries[curr].raw_line)
                    and not is_python_chaining_marker(entries[curr].raw_line)
                ):
                    code_entry = entries[curr]
                    # Check if it's the terminal exception
                    exc_check = detect_python_exception(code_entry.raw_line)
                    if exc_check and not code_entry.raw_line.startswith("    "):
                        break
                    code_entry.category = LineCategory.STACK_FRAME
                    code_entry.failure_event_id = event_id
                    event_lines.append(code_entry)
                    curr += 1
                continue

            # Chaining marker line
            if is_python_chaining_marker(raw):
                e.category = LineCategory.STACK_FRAME
                e.failure_event_id = event_id
                event_lines.append(e)
                curr += 1
                # Following line might be "Traceback (most recent call last):"
                if curr < n and is_python_traceback_header(entries[curr].raw_line):
                    entries[curr].category = LineCategory.TRACEBACK_HEADER
                    entries[curr].failure_event_id = event_id
                    event_lines.append(entries[curr])
                    curr += 1
                continue

            # Terminal exception line
            exc_match = detect_python_exception(raw)
            if exc_match:
                e.category = LineCategory.EXCEPTION
                e.failure_event_id = event_id
                event_lines.append(e)
                terminal_entry = e
                exception_type = exc_match[0]
                exception_msg = exc_match[1] or raw.strip()
                curr += 1

                # Lookahead for chained exception transition marker
                look = curr
                while look < n and not entries[look].raw_line.strip():
                    look += 1
                if look < n and is_python_chaining_marker(entries[look].raw_line):
                    # Consume intervening blank lines and the chaining marker
                    while curr <= look:
                        marker_entry = entries[curr]
                        if is_python_chaining_marker(marker_entry.raw_line):
                            marker_entry.category = LineCategory.STACK_FRAME
                        marker_entry.failure_event_id = event_id
                        event_lines.append(marker_entry)
                        curr += 1

                    # Consume any trailing blank lines and subsequent traceback header
                    while curr < n and not entries[curr].raw_line.strip():
                        blank_entry = entries[curr]
                        blank_entry.failure_event_id = event_id
                        event_lines.append(blank_entry)
                        curr += 1
                    if curr < n and is_python_traceback_header(entries[curr].raw_line):
                        tb_hdr = entries[curr]
                        tb_hdr.category = LineCategory.TRACEBACK_HEADER
                        tb_hdr.failure_event_id = event_id
                        event_lines.append(tb_hdr)
                        curr += 1
                    continue

                break

            # If line is indented context line
            if raw.startswith(" ") or raw.startswith("\t"):
                e.category = LineCategory.STACK_FRAME
                e.failure_event_id = event_id
                event_lines.append(e)
                curr += 1
            else:
                # Reached an unindented, non-exception line
                break

        if not event_lines:
            return None, curr

        primary_entry = terminal_entry or preceding_error or event_lines[0]
        line_numbers = [item.line_number for item in event_lines]
        stack_trace_lines = [
            item.raw_line for item in event_lines if item != preceding_error
        ]

        msg = (
            exception_msg
            if exception_msg
            else (preceding_error.message if preceding_error else primary_entry.message)
        )

        event = FailureEvent(
            event_id=event_id,
            event_type=FailureEventType.EXCEPTION,
            exception_type=exception_type,
            message=msg,
            primary_line_number=primary_entry.line_number,
            start_line_number=line_numbers[0],
            end_line_number=line_numbers[-1],
            line_numbers=line_numbers,
            stack_trace=stack_trace_lines,
            timestamp=preceding_error.timestamp if preceding_error else None,
            level=preceding_error.level if preceding_error else LogLevel.ERROR,
            logger_name=preceding_error.logger_name if preceding_error else None,
        )
        return event, curr

    def _parse_java_trace_event(
        self,
        entries: list[ParsedLogEntry],
        start_idx: int,
        event_num: int,
        preceding_error: ParsedLogEntry | None,
    ) -> tuple[FailureEvent | None, int]:
        """Extract a complete Java stack trace block and build a FailureEvent."""
        event_id = f"event-{event_num}"
        event_lines: list[ParsedLogEntry] = []

        if preceding_error:
            preceding_error.failure_event_id = event_id
            event_lines.append(preceding_error)

        curr = start_idx
        n = len(entries)
        primary_entry = entries[curr]
        primary_entry.category = LineCategory.EXCEPTION
        primary_entry.failure_event_id = event_id
        event_lines.append(primary_entry)

        java_exc = detect_java_exception(primary_entry.raw_line)
        exception_type = java_exc[0] if java_exc else "Exception"
        exception_msg = java_exc[1] if java_exc else primary_entry.raw_line
        curr += 1

        while curr < n:
            e = entries[curr]
            raw = e.raw_line

            if (
                is_java_stack_frame(raw)
                or is_java_truncated_frame(raw)
                or is_java_caused_by(raw)
                or is_java_suppressed(raw)
            ):
                e.category = LineCategory.STACK_FRAME
                e.failure_event_id = event_id
                event_lines.append(e)
                curr += 1
            else:
                break

        line_numbers = [item.line_number for item in event_lines]
        stack_trace_lines = [
            item.raw_line for item in event_lines if item != preceding_error
        ]

        event = FailureEvent(
            event_id=event_id,
            event_type=FailureEventType.EXCEPTION,
            exception_type=exception_type,
            message=exception_msg or primary_entry.message,
            primary_line_number=primary_entry.line_number,
            start_line_number=line_numbers[0],
            end_line_number=line_numbers[-1],
            line_numbers=line_numbers,
            stack_trace=stack_trace_lines,
            timestamp=preceding_error.timestamp
            if preceding_error
            else primary_entry.timestamp,
            level=preceding_error.level if preceding_error else LogLevel.ERROR,
            logger_name=preceding_error.logger_name
            if preceding_error
            else primary_entry.logger_name,
        )
        return event, curr

    def _parse_pytest_failure_event(
        self,
        entries: list[ParsedLogEntry],
        start_idx: int,
        event_num: int,
    ) -> tuple[FailureEvent | None, int]:
        """Extract a pytest failure section (e.g. '____ test_name ____')."""
        event_id = f"event-{event_num}"
        event_lines: list[ParsedLogEntry] = []
        curr = start_idx
        n = len(entries)

        section_header = entries[curr].raw_line.strip("_ ")
        test_name = section_header

        primary_entry: ParsedLogEntry = entries[curr]
        exception_type: str | None = None
        failure_msg: str = f"Test failed: {test_name}"

        while curr < n:
            e = entries[curr]
            raw = e.raw_line

            # Stop at next failure block or summary header
            if curr > start_idx and (
                raw.startswith("____")
                or raw.startswith("====")
                or raw.startswith("FAILED")
            ):
                break

            assertion = detect_assertion_failure(raw)
            if assertion:
                e.category = LineCategory.EXCEPTION
                e.failure_event_id = event_id
                exception_type = assertion[0]
                if assertion[1]:
                    failure_msg = assertion[1]
                primary_entry = e
            else:
                e.category = LineCategory.TEST_FAILURE
                e.failure_event_id = event_id

            event_lines.append(e)
            curr += 1

        line_numbers = [item.line_number for item in event_lines]
        stack_trace_lines = [item.raw_line for item in event_lines]

        event = FailureEvent(
            event_id=event_id,
            event_type=(
                FailureEventType.ASSERTION_FAILURE
                if exception_type == "AssertionError"
                else FailureEventType.TEST_FAILURE
            ),
            exception_type=exception_type or "TestFailure",
            message=failure_msg,
            primary_line_number=primary_entry.line_number,
            start_line_number=line_numbers[0],
            end_line_number=line_numbers[-1],
            line_numbers=line_numbers,
            stack_trace=stack_trace_lines,
            level=LogLevel.ERROR,
        )
        return event, curr

    def _parse_assertion_event(
        self,
        entries: list[ParsedLogEntry],
        start_idx: int,
        event_num: int,
    ) -> tuple[FailureEvent | None, int]:
        """Extract a standalone assertion failure line and surrounding context."""
        event_id = f"event-{event_num}"
        curr = start_idx
        e = entries[curr]
        assertion_info = detect_assertion_failure(e.raw_line)
        exc_type = assertion_info[0] if assertion_info else "AssertionError"
        msg = assertion_info[1] if assertion_info else e.raw_line

        e.category = LineCategory.EXCEPTION
        e.failure_event_id = event_id
        event_lines = [e]
        curr += 1

        # Check if immediately followed by detail lines (e.g. pytest "E   + where ...")
        n = len(entries)
        while curr < n and entries[curr].raw_line.startswith("E "):
            next_e = entries[curr]
            next_e.category = LineCategory.TEST_FAILURE
            next_e.failure_event_id = event_id
            event_lines.append(next_e)
            curr += 1

        line_numbers = [item.line_number for item in event_lines]
        event = FailureEvent(
            event_id=event_id,
            event_type=FailureEventType.ASSERTION_FAILURE,
            exception_type=exc_type,
            message=msg or "Assertion failed",
            primary_line_number=e.line_number,
            start_line_number=line_numbers[0],
            end_line_number=line_numbers[-1],
            line_numbers=line_numbers,
            stack_trace=[item.raw_line for item in event_lines],
            level=LogLevel.ERROR,
        )
        return event, curr


def parse_log_text(log_text: str) -> ParsingResult:
    """Convenience functional interface to parse multiline log text."""
    parser = LogParser()
    return parser.parse(log_text)

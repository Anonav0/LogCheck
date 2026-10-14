"""Tests for Python traceback recognition, frame extraction, and chaining."""

from app.models.failure_event import FailureEventType
from app.models.log_entry import LineCategory, LogLevel
from app.services.log_parser import parse_log_text


class TestPythonTracebackParsing:
    """Verify multiline Python traceback extraction, boundaries, and chaining."""

    def test_single_python_traceback(self) -> None:
        """Verify parsing a standard Python traceback with frames and terminal exception."""
        log = """2026-10-14 08:30:05,432 [ERROR] app.database: Failed to acquire connection
Traceback (most recent call last):
  File "/srv/app/services/payment.py", line 142, in process_transaction
    async with db.transaction() as conn:
  File "/srv/app/database/connection.py", line 88, in transaction
    conn = await self.pool.acquire(timeout=5.0)
app.database.exceptions.ConnectionTimeoutError: Timed out waiting for connection
2026-10-14 08:30:06,001 [INFO] app.server: Health check passed"""

        result = parse_log_text(log)
        assert result.total_lines == 8
        assert result.failure_event_count == 1

        event = result.failure_events[0]
        assert event.event_type == FailureEventType.EXCEPTION
        assert event.exception_type == "ConnectionTimeoutError"
        assert "Timed out waiting for connection" in event.message
        assert event.start_line_number == 1  # Associated preceding ERROR
        assert event.primary_line_number == 7  # Terminal exception declaration line
        assert event.end_line_number == 7

        # Verify subsequent line 8 was NOT absorbed into the failure event!
        last_entry = result.entries[7]
        assert last_entry.line_number == 8
        assert last_entry.level == LogLevel.INFO
        assert last_entry.failure_event_id is None
        assert last_entry.category == LineCategory.NORMAL

    def test_frame_order_preserved(self) -> None:
        """Verify stack frames maintain their exact chronological order."""
        log = """Traceback (most recent call last):
  File "/srv/app/a.py", line 10, in func_a
    func_b()
  File "/srv/app/b.py", line 20, in func_b
    func_c()
  File "/srv/app/c.py", line 30, in func_c
    raise RuntimeError("Deep failure")
RuntimeError: Deep failure"""

        result = parse_log_text(log)
        event = result.failure_events[0]
        assert len(event.stack_trace) == 8
        assert "func_a" in event.stack_trace[1]
        assert "func_b" in event.stack_trace[3]
        assert "func_c" in event.stack_trace[5]

    def test_chained_python_exceptions(self) -> None:
        """Verify exception chaining markers are preserved within the event."""
        log = """Traceback (most recent call last):
  File "/srv/app/db.py", line 15, in query
    raise KeyError("id")
KeyError: 'id'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/srv/app/server.py", line 45, in handle
    query()
  File "/srv/app/db.py", line 18, in query
    raise DatabaseError("Query failed") from exc
DatabaseError: Query failed"""

        result = parse_log_text(log)
        assert result.failure_event_count == 1
        event = result.failure_events[0]
        assert event.exception_type == "DatabaseError"
        assert any(
            "During handling of the above exception" in line
            for line in event.stack_trace
        )

    def test_incomplete_traceback_at_eof(self) -> None:
        """Verify an incomplete or truncated traceback at end of file does not crash."""
        log = """2026-10-14 10:00:00 [ERROR] worker: Crashed
Traceback (most recent call last):
  File "/srv/app/worker.py", line 50, in run"""

        result = parse_log_text(log)
        assert result.failure_event_count == 1
        event = result.failure_events[0]
        assert event.event_type == FailureEventType.EXCEPTION
        assert event.end_line_number == 3

    def test_multiple_independent_python_exceptions(self) -> None:
        """Verify multiple independent tracebacks are identified as distinct failure events."""
        log = """Traceback (most recent call last):
  File "/srv/app/service1.py", line 10, in run
    raise ValueError("Invalid 1")
ValueError: Invalid 1
2026-10-14 09:00:00 [INFO] app.monitor: Processing next job
Traceback (most recent call last):
  File "/srv/app/service2.py", line 20, in run
    raise TypeError("Invalid 2")
TypeError: Invalid 2"""

        result = parse_log_text(log)
        assert result.failure_event_count == 2
        assert result.failure_events[0].exception_type == "ValueError"
        assert result.failure_events[1].exception_type == "TypeError"
        assert result.failure_events[0].event_id != result.failure_events[1].event_id


class TestStackTraceHelpers:
    """Verify lower-level stack trace helper functions."""

    def test_is_stack_frame_line(self) -> None:
        """Verify is_stack_frame_line across python, java, and non-frame lines."""
        from app.services.stack_trace_parser import (
            is_java_caused_by,
            is_java_suppressed,
            is_stack_frame_line,
        )

        py_frame = '  File "/srv/app/main.py", line 42, in run'
        assert is_stack_frame_line(py_frame) is True

        java_frame = "    at com.example.Service.process(Service.java:10)"
        assert is_stack_frame_line(java_frame) is True

        trunc_frame = "    ... 15 more"
        assert is_stack_frame_line(trunc_frame) is True

        assert is_stack_frame_line("Normal log line") is False

        assert is_java_caused_by("Caused by: java.io.IOException") is True
        assert is_java_caused_by("normal line") is False

        assert is_java_suppressed("Suppressed: java.lang.Exception") is True
        assert is_java_suppressed("normal line") is False

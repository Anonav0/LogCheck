"""Advanced log parsing and stack trace tests for Phase 8.

Covers:
- Java exception chains with 'Caused by:' and '... N more' frames
- Java suppressed exceptions ('Suppressed:')
- Python chained exceptions ('During handling...', 'The above exception was...')
- Truncated and incomplete stack traces
- Multiple independent failures in the same log
- Unicode characters in log messages and traces
- Mixed-format logs (JSON + text)
- Source-line integrity and line numbering preservation
"""

from app.models.failure_event import FailureEventType
from app.models.log_entry import LogLevel
from app.services.log_parser import parse_log_text


class TestJavaStackTraces:
    """Tests for complex Java stack traces, nested causes, and suppressed exceptions."""

    def test_java_nested_caused_by_chain(self) -> None:
        raw_log = (
            "2026-10-15 08:00:00.000 [main] ERROR com.example.Service - Fatal service error\n"
            "java.lang.RuntimeException: Wrapper exception occurred\n"
            "\tat com.example.Service.process(Service.java:45)\n"
            "\tat com.example.Service.run(Service.java:20)\n"
            "Caused by: java.sql.SQLException: Connection to database failed\n"
            "\tat com.example.db.Pool.getConnection(Pool.java:102)\n"
            "\tat com.example.Service.process(Service.java:40)\n"
            "\t... 1 more\n"
            "Caused by: java.net.ConnectException: Connection refused\n"
            "\tat java.base/sun.nio.ch.Net.connect0(Native Method)\n"
            "\t... 3 more\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) == 1

        event = result.failure_events[0]
        assert event.event_type == FailureEventType.EXCEPTION
        assert event.exception_type == "RuntimeException"
        assert event.start_line_number == 2
        assert event.end_line_number == 11
        assert len(event.stack_trace) >= 2
        assert any(
            "SQLException" in f or "ConnectException" in f for f in event.stack_trace
        )

    def test_java_suppressed_exceptions(self) -> None:
        raw_log = (
            "2026-10-15 08:01:00 [main] ERROR com.example.App - Failed to close resource\n"
            "java.io.IOException: Primary resource failed\n"
            "\tat com.example.App.execute(App.java:30)\n"
            "Suppressed: java.lang.IllegalStateException: Secondary close failure\n"
            "\tat com.example.App.close(App.java:55)\n"
            "\t... 1 more\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) == 1
        event = result.failure_events[0]
        assert event.start_line_number == 2
        assert event.end_line_number == 6
        assert len(event.stack_trace) >= 2
        assert any("Suppressed:" in f for f in event.stack_trace)

    def test_java_truncated_more_frames(self) -> None:
        raw_log = (
            "ERROR com.example.Worker - Execution died\n"
            "java.lang.NullPointerException: Value was null\n"
            "\tat com.example.Worker.run(Worker.java:12)\n"
            "\t... 42 more\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) == 1
        event = result.failure_events[0]
        assert event.start_line_number == 2
        assert event.end_line_number == 4
        assert event.exception_type == "NullPointerException"


class TestPythonChainedExceptions:
    """Tests for Python 3 exception chaining and incomplete traces."""

    def test_python_context_chaining(self) -> None:
        raw_log = (
            "2026-10-15 09:00:00 [ERROR] worker: Task crashed\n"
            "Traceback (most recent call last):\n"
            '  File "/app/handler.py", line 12, in handle\n'
            "    int('invalid')\n"
            "ValueError: invalid literal for int() with base 10: 'invalid'\n"
            "\n"
            "During handling of the above exception, another exception occurred:\n"
            "\n"
            "Traceback (most recent call last):\n"
            '  File "/app/server.py", line 45, in dispatch\n'
            "    raise RuntimeError('Handler failed')\n"
            "RuntimeError: Handler failed\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) >= 1
        event = result.failure_events[0]
        assert event.start_line_number == 1
        assert event.end_line_number == 12
        assert len(event.stack_trace) >= 2
        assert event.exception_type in ("RuntimeError", "ValueError")

    def test_python_explicit_cause_chaining(self) -> None:
        raw_log = (
            "Traceback (most recent call last):\n"
            '  File "/app/repo.py", line 10, in find\n'
            "    raise KeyError('missing_id')\n"
            "KeyError: 'missing_id'\n"
            "The above exception was the direct cause of the following exception:\n"
            "Traceback (most recent call last):\n"
            '  File "/app/service.py", line 22, in get_user\n'
            "    raise UserNotFoundError('User does not exist') from e\n"
            "UserNotFoundError: User does not exist\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) >= 1
        event = result.failure_events[0]
        assert event.start_line_number == 1
        assert event.end_line_number == 9
        assert len(event.stack_trace) >= 2
        assert event.exception_type in ("UserNotFoundError", "KeyError")

    def test_truncated_python_traceback(self) -> None:
        """Traceback cut off abruptly without trailing exception message."""
        raw_log = (
            "2026-10-15 09:10:00 [ERROR] api: Processing aborted\n"
            "Traceback (most recent call last):\n"
            '  File "/app/worker.py", line 88, in process\n'
            "    do_work()\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) >= 1
        event = result.failure_events[0]
        assert event.start_line_number == 1
        assert event.end_line_number == 4


class TestUnicodeAndFormatDiversity:
    """Tests for Unicode characters, mixed formats, and line integrity."""

    def test_unicode_log_content_and_stack_frames(self) -> None:
        raw_log = (
            "2026-10-15 10:00:00 [ERROR] 🚀 service-auth: 认证失败 (Authentication failed for 用户_123)\n"
            "Traceback (most recent call last):\n"
            '  File "/app/auth/认证.py", line 15, in 登录\n'
            "    raise AuthError('密码错误: Invalid credentials 🔑')\n"
            "AuthError: 密码错误: Invalid credentials 🔑\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) == 1
        event = result.failure_events[0]
        assert event.start_line_number == 1
        assert event.end_line_number == 5
        assert event.exception_type == "AuthError"
        assert "🔑" in event.message

    def test_mixed_json_and_plaintext_traceback(self) -> None:
        raw_log = (
            '{"timestamp": "2026-10-15T10:00:00Z", "level": "INFO", "message": "Health check ok"}\n'
            '{"timestamp": "2026-10-15T10:00:01Z", "level": "ERROR", "message": "Fatal queue stall"}\n'
            "Traceback (most recent call last):\n"
            '  File "/app/queue.py", line 50, in poll\n'
            "    raise QueueTimeoutError('Queue timed out')\n"
            "QueueTimeoutError: Queue timed out\n"
            '{"timestamp": "2026-10-15T10:00:02Z", "level": "INFO", "message": "Recovery attempt"}\n'
        )
        result = parse_log_text(raw_log)
        assert len(result.entries) == 7
        assert len(result.failure_events) == 1
        event = result.failure_events[0]
        assert event.start_line_number == 2
        assert event.end_line_number == 6

    def test_multiple_independent_failures_separated_by_info(self) -> None:
        raw_log = (
            "2026-10-15 10:00:00 ERROR worker.1 - TimeoutError: Worker 1 timed out\n"
            "2026-10-15 10:00:01 INFO worker.1 - Worker 1 restarting\n"
            "2026-10-15 10:00:02 ERROR worker.2 - DatabaseConnectionError: Pool full\n"
            "Traceback (most recent call last):\n"
            '  File "/app/db.py", line 10, in connect\n'
            "    raise DatabaseConnectionError('Pool full')\n"
            "DatabaseConnectionError: Pool full\n"
            "2026-10-15 10:00:03 INFO worker.2 - Worker 2 backoff\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.failure_events) == 2
        assert result.failure_events[0].start_line_number == 1
        assert result.failure_events[0].end_line_number == 1
        assert result.failure_events[1].start_line_number == 3
        assert result.failure_events[1].end_line_number == 7

    def test_blank_lines_preserve_canonical_line_indices(self) -> None:
        raw_log = (
            "2026-10-15 10:00:00 INFO server - Starting\n"
            "\n"
            "\n"
            "2026-10-15 10:00:03 ERROR server - MemoryLimitExceeded: OOM kill\n"
            "\n"
            "2026-10-15 10:00:05 INFO server - Exiting\n"
        )
        result = parse_log_text(raw_log)
        assert len(result.entries) == 6
        assert result.entries[0].line_number == 1
        assert result.entries[1].raw_line == ""
        assert result.entries[1].line_number == 2
        assert result.entries[2].raw_line == ""
        assert result.entries[2].line_number == 3
        assert result.entries[3].line_number == 4
        assert result.entries[3].level == LogLevel.ERROR
        assert len(result.failure_events) == 1
        assert result.failure_events[0].primary_line_number == 4

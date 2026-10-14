"""Tests for Java exception traces, test-runner assertion failures, and detectors."""

from app.models.failure_event import FailureEventType
from app.services.exception_detector import (
    detect_assertion_failure,
    detect_java_exception,
    detect_test_failure_indicator,
)
from app.services.log_parser import parse_log_text


class TestExceptionDetectors:
    """Verify lower-level detector functions."""

    def test_detect_java_exception(self) -> None:
        """Verify Java exception pattern detection."""
        line = "java.lang.NullPointerException: Cannot invoke method on null"
        result = detect_java_exception(line)
        assert result is not None
        assert result[0] == "NullPointerException"
        assert result[1] == "Cannot invoke method on null"

    def test_detect_java_caused_by(self) -> None:
        """Verify Java 'Caused by:' detection."""
        line = "Caused by: java.sql.SQLException: Connection refused"
        result = detect_java_exception(line)
        assert result is not None
        assert result[0] == "SQLException"
        assert result[1] == "Connection refused"

    def test_detect_assertion_failure(self) -> None:
        """Verify pytest and python assertion detection."""
        line = "E       AssertionError: assert 1020.0 == 960.0"
        result = detect_assertion_failure(line)
        assert result is not None
        assert result[0] == "AssertionError"
        assert "assert 1020.0 == 960.0" in result[1]

        generic_line = "AssertionError: Expected true but got false"
        gen_res = detect_assertion_failure(generic_line)
        assert gen_res is not None
        assert gen_res[0] == "AssertionError"

        assert detect_assertion_failure("Normal info line") is None

    def test_detect_test_failure_indicator(self) -> None:
        """Verify pytest and unittest test-failure line detection."""
        pytest_line = "FAILED tests/test_orders.py::test_discount_calculation - AssertionError: assert 1020.0 == 960.0"
        res = detect_test_failure_indicator(pytest_line)
        assert res is not None
        assert "test_discount_calculation" in res[0]

        unittest_line = "FAIL: test_billing (tests.test_billing.TestBilling)"
        res2 = detect_test_failure_indicator(unittest_line)
        assert res2 is not None
        assert "test_billing" in res2[0]

        assert detect_test_failure_indicator("Just normal log") is None
        assert "test_billing" in res2[0]


class TestJavaStackTraceParsing:
    """Verify multiline Java stack trace parsing, caused-by chains, and frames."""

    def test_java_stack_trace_with_frames_and_cause(self) -> None:
        """Verify Java trace with frames, caused-by, and truncation markers."""
        log = """java.lang.NullPointerException: Cannot invoke method on null
    at com.example.PaymentService.process(PaymentService.java:42)
    at com.example.PaymentService.charge(PaymentService.java:18)
Caused by: java.sql.SQLException: Connection refused
    at com.example.db.Pool.getConnection(Pool.java:99)
    ... 12 more
2026-10-14 10:00:00 [INFO] app: Recovery attempted"""

        result = parse_log_text(log)
        assert result.failure_event_count == 1
        event = result.failure_events[0]
        assert event.event_type == FailureEventType.EXCEPTION
        assert event.exception_type == "NullPointerException"
        assert event.start_line_number == 1
        assert event.end_line_number == 6
        assert len(event.stack_trace) == 6

        # Subsequent INFO line should not be part of the failure event
        assert result.entries[6].failure_event_id is None

    def test_incomplete_java_trace_does_not_crash(self) -> None:
        """Verify an incomplete Java trace with only exception line and 1 frame."""
        log = """java.lang.RuntimeException: Unexpected error
    at com.example.Main.main(Main.java:10)"""

        result = parse_log_text(log)
        assert result.failure_event_count == 1
        assert result.failure_events[0].exception_type == "RuntimeException"


class TestTestRunnerFailures:
    """Verify test-runner assertion failure extraction from pytest logs."""

    def test_sample_test_failure_fixture(
        self, sample_test_failure_log_text: str
    ) -> None:
        """Verify parsing sample_test_failure.log captures the failing test event."""
        result = parse_log_text(sample_test_failure_log_text)
        assert result.failure_event_count >= 1

        # Look for the assertion failure event
        assertion_events = [
            e
            for e in result.failure_events
            if e.event_type == FailureEventType.ASSERTION_FAILURE
            or e.exception_type == "AssertionError"
        ]
        assert len(assertion_events) >= 1
        event = assertion_events[0]
        assert "assert 1020.0 == 960.0" in event.message
        assert event.primary_line_number > 0

    def test_informational_failed_does_not_create_failure_event(self) -> None:
        """Verify benign text containing 'failed' does not trigger false failure event."""
        log = "2026-10-14 10:00:00 [INFO] app.health: 0 tests failed in regression run"
        result = parse_log_text(log)
        assert result.failure_event_count == 0
        assert result.error_count == 0

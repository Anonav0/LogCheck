"""Deterministic detection and classification of exceptions, errors, and test failures."""

import re

# Python exception declaration: e.g. "ValueError: Invalid parameter", "app.exceptions.DatabaseError: timeout"
_PY_EXCEPTION_PATTERN = re.compile(
    r"^(?:[a-zA-Z_][a-zA-Z0-9_]*\.)*([a-zA-Z_][a-zA-Z0-9_]*(?:Error|Exception|Warning|Exit|Interrupt|Fault|Timeout))(?::\s*(.*))?$"
)

# Java exception declaration: e.g. "java.lang.NullPointerException: Cannot invoke method", "com.app.CustomException: failed"
_JAVA_EXCEPTION_PATTERN = re.compile(
    r"^(?:[a-zA-Z_][a-zA-Z0-9_]*\.)+([A-Z][a-zA-Z0-9_$]*(?:Exception|Error|Throwable|Fault))(?::\s*(.*))?$"
)

# Java "Caused by:" line
_JAVA_CAUSED_BY_PATTERN = re.compile(
    r"^\s*Caused by:\s*(?:[a-zA-Z_][a-zA-Z0-9_]*\.)*([A-Z][a-zA-Z0-9_$]*(?:Exception|Error|Throwable|Fault))(?::\s*(.*))?$"
)

# Pytest assertion line: e.g. "E       AssertionError: assert 1020.0 == 960.0"
_PYTEST_ASSERTION_PATTERN = re.compile(
    r"^E\s+([a-zA-Z_][a-zA-Z0-9_]*(?:Error|Exception|Failure))(?::\s*(.*))?$"
)

# Generic assertion error line
_GENERIC_ASSERTION_PATTERN = re.compile(
    r"^(?:AssertionError|assert\s+.*)(?::\s*(.*))?$"
)

# Pytest test failure indicator: e.g. "FAILED tests/test_orders.py::test_discount_calculation"
_PYTEST_FAILED_LINE_PATTERN = re.compile(
    r"^FAILED\s+([^\s:]+(?:::([^\s]+))?)(?:\s+-\s+(.*))?$"
)

# Unittest failure indicator: e.g. "FAIL: test_orders (tests.TestOrders)"
_UNITTEST_FAILED_PATTERN = re.compile(
    r"^(?:FAIL|ERROR):\s+([a-zA-Z0-9_]+)\s+\(([^)]+)\)"
)


def detect_python_exception(line: str) -> tuple[str, str] | None:
    """Detect a Python terminal exception declaration line.

    Returns:
        (exception_type, message) or None if not an exception declaration.
    """
    stripped = line.strip()
    match = _PY_EXCEPTION_PATTERN.match(stripped)
    if match:
        exc_type = match.group(1)
        # Avoid treating ordinary sentences starting with Error as exceptions
        # unless formatted as ExceptionType: message or standalone standard name
        msg = match.group(2) if match.group(2) is not None else ""
        return exc_type, msg
    return None


def detect_java_exception(line: str) -> tuple[str, str] | None:
    """Detect a Java exception declaration or 'Caused by:' header.

    Returns:
        (exception_type, message) or None if not a Java exception.
    """
    stripped = line.strip()
    caused_match = _JAVA_CAUSED_BY_PATTERN.match(stripped)
    if caused_match:
        exc_type = caused_match.group(1)
        msg = caused_match.group(2) if caused_match.group(2) is not None else ""
        return exc_type, msg

    match = _JAVA_EXCEPTION_PATTERN.match(stripped)
    if match:
        exc_type = match.group(1)
        msg = match.group(2) if match.group(2) is not None else ""
        return exc_type, msg

    return None


def detect_assertion_failure(line: str) -> tuple[str, str] | None:
    """Detect an assertion failure from pytest or standard python assertion.

    Returns:
        (error_type, message) or None if not an assertion failure.
    """
    stripped = line.strip()
    pytest_match = _PYTEST_ASSERTION_PATTERN.match(stripped)
    if pytest_match:
        return pytest_match.group(1), (pytest_match.group(2) or "")

    generic_match = _GENERIC_ASSERTION_PATTERN.match(stripped)
    if generic_match:
        return "AssertionError", (generic_match.group(1) or stripped)

    return None


def detect_test_failure_indicator(line: str) -> tuple[str, str] | None:
    """Detect a test runner failure line (e.g. pytest FAILED, unittest FAIL/ERROR).

    Returns:
        (test_id, failure_summary) or None if not a test failure.
    """
    stripped = line.strip()
    pytest_match = _PYTEST_FAILED_LINE_PATTERN.match(stripped)
    if pytest_match:
        test_id = pytest_match.group(1)
        summary = pytest_match.group(3) or f"Test failed: {test_id}"
        return test_id, summary

    unittest_match = _UNITTEST_FAILED_PATTERN.match(stripped)
    if unittest_match:
        test_id = f"{unittest_match.group(2)}.{unittest_match.group(1)}"
        return test_id, f"Test failed: {test_id}"

    return None

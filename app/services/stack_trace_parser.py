"""Stack trace identification and frame extraction for Python and Java logs."""

import re

_PY_TRACEBACK_HEADER_PATTERN = re.compile(
    r"^Traceback \(most recent call last\):", re.IGNORECASE
)
_PY_FRAME_PATTERN = re.compile(r'^\s*File "([^"]+)", line (\d+)(?:, in (.+))?')
_PY_CHAIN_MARKERS = {
    "During handling of the above exception, another exception occurred:",
    "The above exception was the direct cause of the following exception:",
}

_JAVA_FRAME_PATTERN = re.compile(r"^\s*at\s+([a-zA-Z0-9_$./]+)\(([^)]*)\)")
_JAVA_TRUNCATED_FRAME_PATTERN = re.compile(r"^\s*\.\.\.\s*\d+\s*more")
_JAVA_CAUSED_BY_PREFIX = "Caused by:"
_JAVA_SUPPRESSED_PREFIX = "Suppressed:"


def is_python_traceback_header(line: str) -> bool:
    """Return True if line is a Python traceback header."""
    return bool(_PY_TRACEBACK_HEADER_PATTERN.match(line.strip()))


def is_python_stack_frame(line: str) -> bool:
    """Return True if line is a Python 'File "...", line X, in Y' frame."""
    return bool(_PY_FRAME_PATTERN.match(line))


def is_python_chaining_marker(line: str) -> bool:
    """Return True if line is a standard Python exception-chaining transition."""
    return line.strip() in _PY_CHAIN_MARKERS


def is_java_stack_frame(line: str) -> bool:
    """Return True if line is a Java 'at com.package.Class.method(File.java:12)' frame."""
    return bool(_JAVA_FRAME_PATTERN.match(line))


def is_java_truncated_frame(line: str) -> bool:
    """Return True if line is a Java truncated stack indicator (e.g. '... 12 more')."""
    return bool(_JAVA_TRUNCATED_FRAME_PATTERN.match(line))


def is_java_caused_by(line: str) -> bool:
    """Return True if line begins with 'Caused by:'."""
    return line.strip().startswith(_JAVA_CAUSED_BY_PREFIX)


def is_java_suppressed(line: str) -> bool:
    """Return True if line begins with 'Suppressed:'."""
    return line.strip().startswith(_JAVA_SUPPRESSED_PREFIX)


def is_stack_frame_line(line: str) -> bool:
    """Determine if a line is an identifiable stack frame line across supported languages."""
    return (
        is_python_stack_frame(line)
        or is_java_stack_frame(line)
        or is_java_truncated_frame(line)
    )


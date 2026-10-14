"""Tests verifying cross-process fingerprint stability and independence from hash seeds."""

import os
import subprocess
import sys

from app.models.failure_event import FailureEvent, FailureEventType
from app.models.log_entry import LogLevel
from app.services.fingerprinting import generate_fingerprint


class TestFingerprintCrossProcessStability:
    """Verify fingerprints do not fluctuate across separate Python process invocations or hash seeds."""

    def test_fingerprint_stability_across_python_processes(self) -> None:
        """Verify fingerprint remains byte-for-byte identical across separate python processes with varied hash seeds."""
        event = FailureEvent(
            event_id="ev-stability-1",
            event_type=FailureEventType.EXCEPTION,
            exception_type="ConnectionTimeoutError",
            message="Timed out waiting for database connection from pool after 5.0s",
            primary_line_number=42,
            start_line_number=40,
            end_line_number=45,
            line_numbers=[40, 41, 42, 43, 44, 45],
            stack_trace=["Traceback...", "File ..."],
            level=LogLevel.ERROR,
            logger_name="app.database",
        )

        in_process_fp = generate_fingerprint(event)
        assert len(in_process_fp) == 64

        script = """
import sys
from app.models.failure_event import FailureEvent, FailureEventType
from app.models.log_entry import LogLevel
from app.services.fingerprinting import generate_fingerprint

event = FailureEvent(
    event_id="ev-stability-99",  # Different ID, should not affect fingerprint
    event_type=FailureEventType.EXCEPTION,
    exception_type="ConnectionTimeoutError",
    message="Timed out waiting for database connection from pool after 5.0s",
    primary_line_number=999,  # Different line, should not affect fingerprint
    start_line_number=900,
    end_line_number=1000,
    line_numbers=[900, 999],
    stack_trace=[],
    level=LogLevel.ERROR,
    logger_name="app.database",
)
print(generate_fingerprint(event))
"""

        # Run with distinct hash seeds to guarantee independence from Python's randomized hash()
        seeds = ["0", "42", "99999", "random"]
        for seed in seeds:
            env = os.environ.copy()
            env["PYTHONHASHSEED"] = seed
            env["PYTHONPATH"] = "."

            res = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            subprocess_fp = res.stdout.strip()
            assert subprocess_fp == in_process_fp, (
                f"Fingerprint mismatch with PYTHONHASHSEED={seed}: {subprocess_fp} != {in_process_fp}"
            )

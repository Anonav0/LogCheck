"""Tests for failure message normalization, signature extraction, and fingerprint generation."""

import re

from app.models.failure_event import FailureEvent, FailureEventType
from app.models.log_entry import LogLevel
from app.services.fingerprinting import (
    extract_failure_signature,
    generate_fingerprint,
    normalize_failure_message,
    serialize_signature,
)


class TestMessageNormalization:
    """Verify safe, conservative normalization of volatile tokens in failure messages."""

    def test_identical_messages_normalize_identically(self) -> None:
        """Verify deterministic normalization of static message strings."""
        msg = "Database connection pool exhausted"
        assert normalize_failure_message(msg) == normalize_failure_message(msg)

    def test_uuid_normalization(self) -> None:
        """Verify standard UUID tokens are replaced with <UUID>."""
        msg1 = "Failed processing request 550e8400-e29b-41d4-a716-446655440000"
        msg2 = "Failed processing request 123e4567-e89b-12d3-a456-426614174000"
        norm1 = normalize_failure_message(msg1)
        norm2 = normalize_failure_message(msg2)
        assert norm1 == "Failed processing request <UUID>"
        assert norm1 == norm2

    def test_memory_address_normalization(self) -> None:
        """Verify hex memory addresses are replaced with <MEMORY_ADDRESS>."""
        msg1 = "Object at 0x7f12ab34 raised an exception"
        msg2 = "Object at 0x00007fa8b9c1 raised an exception"
        norm1 = normalize_failure_message(msg1)
        norm2 = normalize_failure_message(msg2)
        assert norm1 == "Object at <MEMORY_ADDRESS> raised an exception"
        assert norm1 == norm2

    def test_request_id_normalization(self) -> None:
        """Verify request ID prefixes and phrases are normalized."""
        msg1 = "Database connection failed for request req-a1b2c3d4"
        msg2 = "Database connection failed for request req-e5f6g7h8"
        norm1 = normalize_failure_message(msg1)
        norm2 = normalize_failure_message(msg2)
        assert norm1 == "Database connection failed for request <REQUEST_ID>"
        assert norm1 == norm2

        phrase1 = "Failed handling request 12345"
        phrase2 = "Failed handling request 98765"
        assert normalize_failure_message(phrase1) == normalize_failure_message(phrase2)
        assert "request <REQUEST_ID>" in normalize_failure_message(phrase1)

    def test_entity_id_normalization(self) -> None:
        """Verify entity ID tokens (tx-, job-, ord-, Payment N) normalize."""
        assert (
            normalize_failure_message("Payment 10234 failed validation")
            == "Payment <ENTITY_ID> failed validation"
        )
        assert (
            normalize_failure_message("Transaction tx-99128 aborted")
            == "Transaction <TX_ID> aborted"
        )
        assert (
            normalize_failure_message("Task job-981 failed") == "Task <JOB_ID> failed"
        )
        assert (
            normalize_failure_message("Failed for order_id=ord_99011")
            == "Failed for order_id=<ORDER_ID>"
        )

    def test_meaningful_durations_preserved(self) -> None:
        """Verify timeouts/durations are preserved and not blindly replaced."""
        msg5 = "Connection timeout after 5 seconds"
        msg60 = "Connection timeout after 60 seconds"
        assert normalize_failure_message(msg5) != normalize_failure_message(msg60)
        assert "5 seconds" in normalize_failure_message(msg5)
        assert "60 seconds" in normalize_failure_message(msg60)

    def test_http_status_codes_preserved(self) -> None:
        """Verify distinct HTTP status codes remain distinct."""
        msg_503 = "503 Service Unavailable: Gateway upstream overloaded"
        msg_404 = "404 Not Found: Resource missing"
        assert normalize_failure_message(msg_503) != normalize_failure_message(msg_404)
        assert "503" in normalize_failure_message(msg_503)
        assert "404" in normalize_failure_message(msg_404)

    def test_database_error_codes_preserved(self) -> None:
        """Verify database error codes remain preserved."""
        ora1 = "Database error ORA-00001: unique constraint violated"
        ora2 = "Database error ORA-00942: table or view does not exist"
        assert normalize_failure_message(ora1) != normalize_failure_message(ora2)

    def test_empty_and_none_messages_handled_safely(self) -> None:
        """Verify empty and None messages return empty string without error."""
        assert normalize_failure_message("") == ""
        assert normalize_failure_message(None) == ""
        assert normalize_failure_message("   ") == ""


class TestFingerprintGeneration:
    """Verify SHA-256 fingerprint generation, canonical serialization, and stability."""

    def _make_event(
        self,
        event_id: str = "event-1",
        event_type: FailureEventType = FailureEventType.EXCEPTION,
        exception_type: str | None = "ValueError",
        message: str = "Invalid parameter",
        primary_line: int = 10,
        timestamp: str | None = "2026-10-14 10:00:00",
        logger_name: str | None = "app.service",
    ) -> FailureEvent:
        return FailureEvent(
            event_id=event_id,
            event_type=event_type,
            exception_type=exception_type,
            message=message,
            primary_line_number=primary_line,
            start_line_number=primary_line,
            end_line_number=primary_line,
            line_numbers=[primary_line],
            stack_trace=[],
            timestamp=timestamp,
            level=LogLevel.ERROR,
            logger_name=logger_name,
        )

    def test_identical_events_generate_identical_fingerprints(self) -> None:
        """Verify same failure pattern yields identical SHA-256 fingerprint."""
        ev1 = self._make_event()
        ev2 = self._make_event(event_id="event-2")
        assert generate_fingerprint(ev1) == generate_fingerprint(ev2)

    def test_normalized_variables_do_not_affect_fingerprint(self) -> None:
        """Verify events differing only by variable IDs receive identical fingerprints."""
        ev1 = self._make_event(
            event_id="ev-1",
            exception_type="DatabaseConnectionError",
            message="Database connection failed for request req-a1b2c3d4",
        )
        ev2 = self._make_event(
            event_id="ev-2",
            exception_type="DatabaseConnectionError",
            message="Database connection failed for request req-e5f6g7h8",
        )
        assert generate_fingerprint(ev1) == generate_fingerprint(ev2)

    def test_different_exception_types_generate_different_fingerprints(self) -> None:
        """Verify ValueError vs TypeError yield distinct fingerprints even with matching messages."""
        ev1 = self._make_event(exception_type="ValueError", message="Invalid input")
        ev2 = self._make_event(exception_type="TypeError", message="Invalid input")
        assert generate_fingerprint(ev1) != generate_fingerprint(ev2)

    def test_different_messages_generate_different_fingerprints(self) -> None:
        """Verify semantic message differences yield distinct fingerprints."""
        ev1 = self._make_event(message="Timeout after 5 seconds")
        ev2 = self._make_event(message="Timeout after 60 seconds")
        assert generate_fingerprint(ev1) != generate_fingerprint(ev2)

    def test_line_numbers_and_timestamps_do_not_affect_fingerprint(self) -> None:
        """Verify occurrence line numbers and timestamps do not alter fingerprint."""
        ev1 = self._make_event(primary_line=10, timestamp="2026-10-14 08:00:00")
        ev2 = self._make_event(primary_line=999, timestamp="2026-10-14 23:59:59")
        assert generate_fingerprint(ev1) == generate_fingerprint(ev2)

    def test_fingerprint_is_valid_64_char_sha256(self) -> None:
        """Verify fingerprint is a valid 64-character lowercase hexadecimal string."""
        ev = self._make_event()
        fp = generate_fingerprint(ev)
        assert len(fp) == 64
        assert re.match(r"^[0-9a-f]{64}$", fp) is not None

    def test_canonical_serialization_determinism(self) -> None:
        """Verify serialize_signature produces consistent output regardless of instantiation."""
        ev = self._make_event(
            exception_type="KeyError",
            message="Key 'token' not found",
            logger_name="app.auth",
        )
        sig1 = extract_failure_signature(ev)
        sig2 = extract_failure_signature(ev)
        assert serialize_signature(sig1) == serialize_signature(sig2)
        assert serialize_signature(sig1) == (
            "category=exception|component=app.auth|exception=KeyError|message=Key 'token' not found"
        )

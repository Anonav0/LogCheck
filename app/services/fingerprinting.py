"""Deterministic failure signature extraction, normalization, and fingerprint generation."""

import hashlib
import re
from dataclasses import dataclass

from app.models.failure_event import FailureEvent

# Regular expressions for safe normalization of volatile identifiers
# 1. UUIDs: 8-4-4-4-12 hex format
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# 2. Hexadecimal memory addresses: e.g. 0x7f12ab34, 0x00007fa8b9c1d2e0
_MEMORY_ADDRESS_PATTERN = re.compile(r"\b0x[0-9a-fA-F]{4,16}\b")

# 3. Request identifiers: e.g. req-a1b2c3d4, req_12345
_REQUEST_PREFIX_PATTERN = re.compile(r"\breq-[a-zA-Z0-9_-]+\b")

# 4. Contextual request phrases: e.g. "request 12345", "request req-1234", "request: 99128"
_REQUEST_PHRASE_PATTERN = re.compile(
    r"\b(request\s+(?:id\s*[:=]?\s*|[#=]\s*)?)[a-zA-Z0-9_-]+\b",
    re.IGNORECASE,
)

# 5. Entity ID tokens: tx-99128, job-981, ord-123
_TX_PATTERN = re.compile(r"\btx-[a-zA-Z0-9_-]+\b")
_JOB_PATTERN = re.compile(r"\bjob-[a-zA-Z0-9_-]+\b")
_ORDER_PATTERN = re.compile(r"\border_id=ord_[a-zA-Z0-9_-]+\b")

# 6. Entity identification phrases: e.g. "Payment 10234", "user 105", "users/42"
_PAYMENT_ENTITY_PATTERN = re.compile(r"\b(Payment\s+)\d+\b")
_USER_ENTITY_PATTERN = re.compile(r"\b(users?/)\d+\b")
_USER_ID_PARAM_PATTERN = re.compile(r'\buser_id=["\']?[a-zA-Z0-9_-]+["\']?')

# Multi-space collapse
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_failure_message(message: str | None) -> str:
    """Normalize variable values in a failure message without destroying semantic meaning.

    Normalizes:
        - UUIDs -> <UUID>
        - Memory addresses -> <MEMORY_ADDRESS>
        - Specific request tokens and phrases -> <REQUEST_ID>
        - Transaction / job / order tokens -> <TX_ID>, <JOB_ID>, etc.
        - Entity identifiers (e.g. "Payment 10234" -> "Payment <ENTITY_ID>")

    Preserves:
        - Timeouts / durations ("after 5 seconds" vs "after 60 seconds")
        - HTTP status codes ("503 Service Unavailable", "404 Not Found")
        - Database error codes ("ORA-00001", "SQLSTATE 23505")
        - Version numbers ("Python 3.12.3")
        - Port numbers ("port 8000")
        - Assertion expressions ("assert 1020.0 == 960.0")
    """
    if not message:
        return ""

    text = message.strip()

    # 1. UUID normalization
    text = _UUID_PATTERN.sub("<UUID>", text)

    # 2. Memory address normalization
    text = _MEMORY_ADDRESS_PATTERN.sub("<MEMORY_ADDRESS>", text)

    # 3. Contextual request phrase normalization ("request 12345" -> "request <REQUEST_ID>")
    text = _REQUEST_PHRASE_PATTERN.sub(r"\1<REQUEST_ID>", text)

    # 4. Request tokens ("req-a1b2c3d4" -> "<REQUEST_ID>")
    text = _REQUEST_PREFIX_PATTERN.sub("<REQUEST_ID>", text)

    # 5. Entity tokens
    text = _TX_PATTERN.sub("<TX_ID>", text)
    text = _JOB_PATTERN.sub("<JOB_ID>", text)
    text = _ORDER_PATTERN.sub("order_id=<ORDER_ID>", text)

    # 6. Entity phrases
    text = _PAYMENT_ENTITY_PATTERN.sub(r"\1<ENTITY_ID>", text)
    text = _USER_ENTITY_PATTERN.sub(r"\1<ENTITY_ID>", text)
    text = _USER_ID_PARAM_PATTERN.sub("user_id=<USER_ID>", text)

    # 7. Collapse whitespace
    text = _WHITESPACE_PATTERN.sub(" ", text).strip()

    return text


@dataclass(frozen=True)
class FailureSignature:
    """Deterministic canonical representation of a failure pattern."""

    failure_type: str
    exception_type: str | None
    normalized_message: str
    component: str | None


def extract_failure_signature(event: FailureEvent) -> FailureSignature:
    """Extract a canonical FailureSignature from a FailureEvent."""
    normalized_msg = normalize_failure_message(event.message)

    return FailureSignature(
        failure_type=event.event_type.value,
        exception_type=event.exception_type.strip() if event.exception_type else None,
        normalized_message=normalized_msg,
        component=event.logger_name.strip() if event.logger_name else None,
    )


def serialize_signature(signature: FailureSignature) -> str:
    """Serialize FailureSignature to a canonical, deterministic string for hashing.

    Format ensures consistent key ordering and avoids object identity or locale dependency:
        category=<type>|component=<comp>|exception=<exc>|message=<msg>
    """
    cat = signature.failure_type
    comp = signature.component or ""
    exc = signature.exception_type or ""
    msg = signature.normalized_message
    return f"category={cat}|component={comp}|exception={exc}|message={msg}"


def generate_fingerprint(event: FailureEvent) -> str:
    """Generate a stable 64-character SHA-256 fingerprint for a FailureEvent.

    The fingerprint is deterministic across runs, independent of Python's hash seed,
    and unaffected by line numbers, timestamps, or occurrence order.
    """
    signature = extract_failure_signature(event)
    canonical = serialize_signature(signature)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


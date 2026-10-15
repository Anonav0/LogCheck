"""HTTP API client for LogLens AI Streamlit dashboard.

Communicates with the FastAPI backend endpoints (health, readiness, and analysis).
Handles network failures, timeouts, and HTTP status codes cleanly without leaking
sensitive backend details or crashing the UI.
"""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_ANALYSIS_TIMEOUT = 65.0


def get_api_base_url() -> str:
    """Retrieve configured API base URL from environment or default."""
    return os.environ.get("LOGLENS_API_URL", DEFAULT_API_URL).rstrip("/")


def _parse_error_response(response: requests.Response) -> str:
    """Extract a user-friendly error description from an HTTP error response."""
    status_code = response.status_code
    try:
        data = response.json()
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            code = err.get("code", "ERROR")
            msg = err.get("message", "An error occurred.")
            limit = err.get("limit")
            actual = err.get("actual")
            if limit is not None and actual is not None:
                return f"[{code}] {msg} (Limit: {limit:,}, Actual: {actual:,})"
            return f"[{code}] {msg}"
        if isinstance(data, dict) and "detail" in data:
            return f"Error ({status_code}): {data['detail']}"
    except Exception:
        pass

    if status_code == 413:
        return "Payload Too Large (HTTP 413): The submitted log exceeds the server size or line count limits."
    if status_code == 422:
        return "Validation Error (HTTP 422): The submitted log input or parameters were invalid."
    if status_code == 400:
        return "Bad Request (HTTP 400): Malformed request payload."
    if status_code == 429:
        return "Too Many Requests (HTTP 429): Rate limit exceeded. Please wait before retrying."
    if status_code == 503:
        return "Service Unavailable (HTTP 503): Backend service is temporarily unavailable."
    if status_code >= 500:
        return f"Server Error (HTTP {status_code}): The backend encountered an unexpected error."

    return f"Request failed with HTTP {status_code}."


def check_health(
    base_url: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Execute GET /health liveness probe.

    Returns:
        (data, None) on success, or (None, error_message) on failure.
    """
    url = f"{base_url or get_api_base_url()}/health"
    try:
        resp = requests.get(url, timeout=DEFAULT_CONNECT_TIMEOUT)
        if resp.status_code == 200:
            return resp.json(), None
        return None, _parse_error_response(resp)
    except requests.exceptions.ConnectionError:
        return (
            None,
            f"Could not connect to LogLens AI API at {url}. Please ensure the backend is running.",
        )
    except requests.exceptions.Timeout:
        return None, f"Health check timed out after {DEFAULT_CONNECT_TIMEOUT}s."
    except Exception as exc:
        return None, f"Health check failed: {exc!s}"


def check_readiness(
    base_url: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Execute GET /health/ready readiness probe.

    Returns:
        (data, None) on success, or (None, error_message) on failure.
    """
    url = f"{base_url or get_api_base_url()}/health/ready"
    try:
        resp = requests.get(url, timeout=DEFAULT_CONNECT_TIMEOUT)
        if resp.status_code == 200:
            return resp.json(), None
        return None, _parse_error_response(resp)
    except requests.exceptions.ConnectionError:
        return (
            None,
            f"Could not connect to LogLens AI API at {url}. Please ensure the backend is running.",
        )
    except requests.exceptions.Timeout:
        return None, f"Readiness check timed out after {DEFAULT_CONNECT_TIMEOUT}s."
    except Exception as exc:
        return None, f"Readiness check failed: {exc!s}"


def analyze_logs(
    log_text: str,
    include_ai: bool = False,
    base_url: str | None = None,
    timeout: float = DEFAULT_ANALYSIS_TIMEOUT,
) -> tuple[dict[str, Any] | None, str | None]:
    """Execute POST /api/v1/analyze for log payload analysis.

    Args:
        log_text: Raw log content to analyze.
        include_ai: Whether to request AI triage.
        base_url: Override base URL if provided.
        timeout: Request timeout in seconds.

    Returns:
        (analysis_response_dict, None) on success, or (None, error_message) on failure.
    """
    url = f"{base_url or get_api_base_url()}/api/v1/analyze"
    payload = {"log_text": log_text, "include_ai": include_ai}

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            try:
                return resp.json(), None
            except Exception:
                return (
                    None,
                    "Backend returned HTTP 200 but response body was not valid JSON.",
                )
        return None, _parse_error_response(resp)
    except requests.exceptions.ConnectionError:
        return (
            None,
            f"Cannot connect to LogLens AI API at {url}. "
            "Please ensure the FastAPI server is running (e.g. `uvicorn app.main:app --reload`).",
        )
    except requests.exceptions.Timeout:
        return (
            None,
            f"Analysis request timed out after {timeout:.0f} seconds. "
            "If analyzing a large log with AI, the LLM provider may be slow or unresponsive.",
        )
    except Exception as exc:
        return None, f"Unexpected error during API analysis call: {exc!s}"

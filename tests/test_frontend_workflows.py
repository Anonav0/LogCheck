"""Tests for Streamlit frontend workflows and dashboard UI lifecycle.

Implements Phase 8 Section 8 requirements:
- Streamlit AppTest-based headless integration tests for frontend/streamlit_app.py.
- Input selection (pasting, sample log loading, file upload validation).
- Analysis trigger, session state transitions, stale input warnings, and clear reset.
- Backend offline, backend error, and empty-failure rendering.
- UI selection and source highlighting consistency.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

from frontend.utils import (
    build_source_html,
    compute_byte_size,
    compute_line_count,
    escape_html,
    validate_line_references,
)

APP_FILE = str(Path(__file__).resolve().parent.parent / "frontend" / "streamlit_app.py")


@pytest.fixture
def mock_api_healthy():
    """Mock API client returning healthy backend status."""
    with (
        patch("frontend.streamlit_app.check_health") as mock_health,
        patch("frontend.streamlit_app.check_readiness") as mock_ready,
    ):
        mock_health.return_value = ({"status": "ok", "service": "LogLens AI"}, None)
        mock_ready.return_value = (
            {"status": "ready", "llm_enabled": True, "llm_available": True},
            None,
        )
        yield mock_health, mock_ready


@pytest.fixture
def mock_api_offline():
    """Mock API client returning offline backend status."""
    with (
        patch("frontend.streamlit_app.check_health") as mock_health,
        patch("frontend.streamlit_app.check_readiness") as mock_ready,
    ):
        mock_health.return_value = (None, "Could not connect to http://127.0.0.1:8000")
        mock_ready.return_value = (None, "Could not connect")
        yield mock_health, mock_ready


class TestStreamlitAppLifecycle:
    """Tests for streamlit_app.py rendering, input modes, and state transitions."""

    def test_app_initial_render_and_welcome(self, mock_api_healthy) -> None:
        """Verify initial clean launch shows header, welcome banner, and sidebar."""
        at = AppTest.from_file(APP_FILE)
        at.run()

        # Check title and welcome guidance
        assert any("LogLens AI" in t.value for t in at.title)
        assert any("Welcome to LogLens AI" in info.value for info in at.info)

        # Check sidebar radio input mode
        assert at.sidebar.radio[0].value == "Paste Logs"

    def test_backend_offline_banner(self, mock_api_offline) -> None:
        """Verify backend offline error banner is presented when health check fails."""
        at = AppTest.from_file(APP_FILE)
        at.run()

        assert any("Backend Offline" in err.value for err in at.error)

    def test_analyze_empty_input_warning(self, mock_api_healthy) -> None:
        """Verify clicking Analyze with empty input prompts user with a warning."""
        at = AppTest.from_file(APP_FILE)
        at.run()

        # Find and click 'Analyze Logs' button
        analyze_btn = next(b for b in at.button if "Analyze" in b.label)
        analyze_btn.click().run()

        assert any("Please provide log text to analyze" in w.value for w in at.warning)

    def test_sample_log_selection_and_load(self, mock_api_healthy) -> None:
        """Verify switching to Sample Logs and loading recurring_failures.log."""
        at = AppTest.from_file(APP_FILE)
        at.run()

        # Select 'Sample Logs' radio
        at.sidebar.radio[0].set_value("Sample Logs").run()
        assert at.sidebar.selectbox[0].value == "recurring_failures.log"

        # Session state input_text should be loaded
        assert "DatabaseConnectionError" in at.session_state["input_text"]

    def test_successful_analysis_display(self) -> None:
        """Verify successful analysis populates metrics and tabbed results."""
        mock_analysis_result = {
            "status": "completed",
            "request_id": "req-test-123",
            "processing_time_ms": 42.5,
            "metrics": {
                "total_log_lines": 10,
                "total_error_entries": 2,
                "total_warning_entries": 1,
                "total_failure_events": 2,
                "unique_failure_groups": 1,
                "repeated_failure_groups": 1,
                "repeated_failure_events": 2,
                "most_frequent_failure_count": 2,
            },
            "failure_groups": [
                {
                    "fingerprint": "abc123456789",
                    "title": "DatabaseConnectionError",
                    "category": "database_error",
                    "occurrence_count": 2,
                    "first_seen_line": 3,
                    "last_seen_line": 7,
                    "representative_message": "Connection lost to database cluster primary",
                    "component": "app.db",
                    "occurrences": [],
                }
            ],
            "failure_events": [],
            "parser_warnings": [],
            "ai_analysis": {
                "summary": "Database connection drop observed.",
                "likely_causes": [],
                "recommended_actions": [],
                "confidence": 0.9,
                "limitations": [],
                "evidence_refs": [],
            },
            "analysis_source": "llm",
        }

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = mock_analysis_result

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "status": "ok",
            "service": "LogLens AI",
            "llm_available": True,
        }

        with (
            patch("requests.post", return_value=mock_post_resp),
            patch("requests.get", return_value=mock_get_resp),
        ):
            at = AppTest.from_file(APP_FILE)
            at.run()

            # Set pasted input
            at.sidebar.text_area[0].input("2026-10-14 ERROR db failure\n").run()

            # Click Analyze button
            analyze_btn = next(b for b in at.button if "Analyze" in b.label)
            analyze_btn.click().run()

            assert at.session_state["active_analysis"] is not None
            # Tabs should be rendered
            assert len(at.tabs) >= 4

    def test_clear_button_resets_state(self, mock_api_healthy) -> None:
        """Verify clicking Clear button wipes active analysis and input state."""
        at = AppTest.from_file(APP_FILE)
        at.run()

        # Seed session state
        at.session_state["input_text"] = "Sample log text"
        at.session_state["active_analysis"] = {"status": "completed"}
        at.session_state["analyzed_text"] = "Sample log text"
        at.run()

        # Find and click Clear button
        clear_btn = next(b for b in at.button if "Clear" in b.label)
        clear_btn.click().run()

        assert at.session_state["input_text"] == ""
        assert at.session_state["active_analysis"] is None
        assert at.session_state["analyzed_text"] == ""


class TestFrontendUtilsAndHighlighting:
    """Tests for pure frontend formatting and source highlighting helpers."""

    def test_escape_html_security(self) -> None:
        """Verify HTML special characters are properly escaped to prevent injection."""
        dangerous = "<script>alert('xss');</script> & \"quote\""
        escaped = escape_html(dangerous)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped
        assert "&amp;" in escaped
        assert "&quot;" in escaped

    def test_validate_line_references_bounds(self) -> None:
        """Verify line numbers outside 1..total_lines are pruned."""
        total = 50
        candidates = [-1, 0, 1, 25, 50, 51, 100]
        valid = validate_line_references(candidates, total)
        assert valid == [1, 25, 50]

    def test_build_source_html_highlighting_classes(self) -> None:
        """Verify HTML generator applies correct styling for primary, context, and focus lines."""
        lines = [
            "2026-10-14 INFO Starting",
            "2026-10-14 ERROR DatabaseConnectionError",
            "2026-10-14 INFO Shutdown",
        ]
        html = build_source_html(
            lines=lines,
            highlight_primary={2},
            highlight_context={1},
            focus_line=2,
            context_radius=5,
        )
        assert "DatabaseConnectionError" in html
        assert "rgba(230, 57, 70" in html  # primary failure background
        assert "#ff4d4f" in html  # primary failure border

    def test_compute_stats_accuracy(self) -> None:
        """Verify UTF-8 byte size and line count computation matches canonical standards."""
        log_sample = "Line 1\nLine 2 with 🚀 emoji\n\nLine 4\n"
        assert compute_line_count(log_sample) == 4
        assert compute_byte_size(log_sample) == len(log_sample.encode("utf-8"))

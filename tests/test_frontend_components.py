"""Tests for Streamlit dashboard UI components."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frontend.components.ai_insights import render_ai_insights
from frontend.components.failure_groups import render_failure_groups
from frontend.components.metrics import render_metrics
from frontend.components.source_viewer import render_source_viewer
from frontend.components.stack_trace import render_stack_traces


@patch("streamlit.columns")
@patch("streamlit.metric")
def test_render_metrics(mock_metric: MagicMock, mock_columns: MagicMock) -> None:
    """Test render_metrics renders cards without error."""
    mock_columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]

    metrics = {
        "total_log_lines": 120,
        "total_error_entries": 4,
        "total_warning_entries": 2,
        "total_failure_events": 3,
        "unique_failure_groups": 2,
        "repeated_failure_groups": 1,
        "repeated_failure_events": 2,
        "most_frequent_failure_count": 2,
    }

    render_metrics(metrics)
    assert mock_metric.call_count == 8


@patch("streamlit.info")
def test_render_failure_groups_empty(mock_info: MagicMock) -> None:
    """Test render_failure_groups handles empty failure group list cleanly."""
    render_failure_groups([], [])
    mock_info.assert_called_once()
    assert "No failure groups were detected" in mock_info.call_args[0][0]


@patch("streamlit.session_state", {})
@patch("streamlit.selectbox")
@patch("streamlit.subheader")
@patch("streamlit.container")
@patch("streamlit.markdown")
@patch("streamlit.columns")
def test_render_failure_groups_populated(
    mock_columns: MagicMock,
    mock_markdown: MagicMock,
    mock_container: MagicMock,
    mock_subheader: MagicMock,
    mock_selectbox: MagicMock,
) -> None:
    mock_columns.side_effect = lambda n: [
        MagicMock() for _ in range(n if isinstance(n, int) else len(n))
    ]
    mock_selectbox.side_effect = [
        "Most frequent first",  # sort choice
        0,  # group index
        0,  # occurrence index
    ]

    groups = [
        {
            "fingerprint": "abc123def456" * 5,
            "title": "DatabaseConnectionError in db.pool",
            "failure_category": "exception",
            "representative_message": "Connection refused to database",
            "occurrence_count": 2,
            "first_seen_line": 10,
            "last_seen_line": 25,
            "severity": "ERROR",
            "component": "db.pool",
            "occurrences": [
                {
                    "event_id": "fe_001",
                    "primary_line_number": 10,
                    "start_line_number": 10,
                    "end_line_number": 12,
                    "original_message": "Connection refused",
                }
            ],
        }
    ]
    events = [
        {
            "event_id": "fe_001",
            "primary_line_number": 10,
            "start_line_number": 10,
            "end_line_number": 12,
            "stack_trace": ["Traceback...", "  File 'db.py', line 10"],
        }
    ]

    render_failure_groups(groups, events)
    mock_subheader.assert_called_once()


@patch("streamlit.markdown")
@patch("streamlit.expander")
@patch("streamlit.code")
def test_render_stack_traces(
    mock_code: MagicMock,
    mock_expander: MagicMock,
    mock_markdown: MagicMock,
) -> None:
    """Test render_stack_traces displays stack traces for selected group."""
    events = [
        {
            "event_id": "fe_001",
            "primary_line_number": 10,
            "message": "Connection failed",
            "exception_type": "ConnectionError",
            "stack_trace": [
                "Traceback (most recent call last):",
                "  raise ConnectionError",
            ],
            "line_numbers": [10, 11, 12],
        }
    ]
    group = {"occurrences": [{"event_id": "fe_001"}]}

    render_stack_traces(events, selected_group=group)
    mock_code.assert_called_once()
    assert "Traceback" in mock_code.call_args[0][0]


@patch("streamlit.info")
def test_render_source_viewer_empty(mock_info: MagicMock) -> None:
    """Test render_source_viewer handles empty text."""
    render_source_viewer("")
    mock_info.assert_called_once()


@patch("streamlit.subheader")
@patch("streamlit.columns")
@patch("streamlit.radio")
@patch("streamlit.number_input")
@patch("streamlit.markdown")
def test_render_source_viewer_populated(
    mock_markdown: MagicMock,
    mock_number_input: MagicMock,
    mock_radio: MagicMock,
    mock_columns: MagicMock,
    mock_subheader: MagicMock,
) -> None:
    """Test render_source_viewer with valid log text and highlights."""
    mock_columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
    mock_radio.return_value = "Full Log"
    mock_number_input.return_value = 1

    sample_log = "2026-10-14 10:00:00 INFO starting\n2026-10-14 10:00:01 ERROR fail\n"
    group = {"first_seen_line": 2, "line_numbers": [2]}

    render_source_viewer(sample_log, selected_group=group)
    mock_subheader.assert_called_once()
    assert mock_markdown.call_count >= 1


@patch("streamlit.info")
def test_render_ai_insights_not_requested(mock_info: MagicMock) -> None:
    """Test render_ai_insights when AI was not requested."""
    render_ai_insights(None, analysis_source="none")
    mock_info.assert_called_once()
    assert "AI Analysis was not requested" in mock_info.call_args[0][0]


@patch("streamlit.warning")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.metric")
@patch("streamlit.progress")
@patch("streamlit.expander")
def test_render_ai_insights_fallback(
    mock_expander: MagicMock,
    mock_progress: MagicMock,
    mock_metric: MagicMock,
    mock_columns: MagicMock,
    mock_markdown: MagicMock,
    mock_warning: MagicMock,
) -> None:
    """Test render_ai_insights when deterministic fallback is active."""
    mock_columns.return_value = [MagicMock(), MagicMock()]
    ai_data = {
        "summary": "Deterministic failure analysis identified 1 failure pattern.",
        "confidence": 0.5,
        "likely_causes": [
            {
                "description": "Database connection drop",
                "reasoning": "Connection timeout indicated on port 5432.",
                "evidence_refs": [
                    {"line_number": 2, "excerpt": "ERROR Connection failed"}
                ],
            }
        ],
        "recommended_actions": [
            {
                "action": "Check database health",
                "rationale": "Verify Postgres daemon status.",
                "priority": "high",
                "evidence_refs": [],
            }
        ],
        "evidence_refs": [],
        "limitations": ["Fallback mode active"],
    }

    render_ai_insights(
        ai_data, analysis_source="fallback", status="completed_with_fallback"
    )
    mock_warning.assert_called_once()
    assert "Deterministic Fallback Analysis" in mock_warning.call_args[0][0]


@patch("streamlit.success")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.metric")
@patch("streamlit.progress")
@patch("streamlit.expander")
def test_render_ai_insights_llm(
    mock_expander: MagicMock,
    mock_progress: MagicMock,
    mock_metric: MagicMock,
    mock_columns: MagicMock,
    mock_markdown: MagicMock,
    mock_success: MagicMock,
) -> None:
    """Test render_ai_insights when LLM analysis is active."""
    mock_columns.return_value = [MagicMock(), MagicMock()]
    ai_data = {
        "summary": "Primary issue is an unhandled NullPointerException.",
        "confidence": 0.95,
        "likely_causes": [],
        "recommended_actions": [],
        "evidence_refs": [],
        "limitations": [],
    }

    render_ai_insights(ai_data, analysis_source="llm", status="completed")
    mock_success.assert_called_once()
    assert "AI-Assisted Triage Report" in mock_success.call_args[0][0]

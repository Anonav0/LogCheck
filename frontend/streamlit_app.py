"""LogLens AI — Streamlit Dashboard Entry Point.

Interactive dashboard for intelligent log analysis, recurring failure grouping,
and evidence-anchored AI triage via FastAPI REST API.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is in sys.path so `frontend` package resolves
# when executed via `streamlit run frontend/streamlit_app.py` or directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from frontend.api_client import (
    analyze_logs,
    check_health,
    check_readiness,
    get_api_base_url,
)
from frontend.components import (
    render_ai_insights,
    render_failure_groups,
    render_metrics,
    render_source_viewer,
    render_stack_traces,
)
from frontend.utils import (
    compute_byte_size,
    compute_line_count,
    format_duration_ms,
)

# Project root fixture directory for safe sample log loading
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

# Known client-side limits (authoritative limits enforced by API)
MAX_RECOMMENDED_BYTES = 1_048_576  # 1 MiB
MAX_RECOMMENDED_LINES = 20_000

# Streamlit Page Configuration
st.set_page_config(
    page_title="LogLens AI — Application Log Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init_session_state() -> None:
    """Initialize necessary session state variables."""
    if "input_text" not in st.session_state:
        st.session_state["input_text"] = ""
    if "active_analysis" not in st.session_state:
        st.session_state["active_analysis"] = None
    if "analyzed_text" not in st.session_state:
        st.session_state["analyzed_text"] = ""
    if "_selected_group" not in st.session_state:
        st.session_state["_selected_group"] = None
    if "_selected_occurrence" not in st.session_state:
        st.session_state["_selected_occurrence"] = None
    if "_selected_ai_line" not in st.session_state:
        st.session_state["_selected_ai_line"] = None


def _load_sample_log(filename: str) -> str:
    """Safely load sample log content from fixtures directory."""
    target_path = FIXTURES_DIR / filename
    if target_path.exists() and target_path.is_file():
        return target_path.read_text(encoding="utf-8")
    return ""


def main() -> None:
    """Main dashboard rendering loop."""
    _init_session_state()

    # 1. Header & Operational Status
    col_title, col_status = st.columns([3, 2])
    with col_title:
        st.title("🔍 LogLens AI")
        st.caption("Understand failures. Find recurring patterns. Trace the evidence.")

    with col_status:
        # Check backend connectivity & readiness
        api_url = get_api_base_url()
        health_data, health_err = check_health(api_url)
        ready_data, _ = check_readiness(api_url)

        if health_err:
            st.error(
                f"🔴 Backend Offline\n\nCannot reach `{api_url}`. Start backend with:\n`uvicorn app.main:app`"
            )
            llm_state = "Unavailable"
        else:
            st.success(f"🟢 API Connected (`{api_url}`)")
            if ready_data:
                if ready_data.get("llm_available"):
                    llm_state = "Ready (Mock / Provider Configured)"
                elif ready_data.get("llm_enabled"):
                    llm_state = "Enabled (No API Key, fallback active)"
                else:
                    llm_state = "Disabled (Deterministic fallback)"
            else:
                llm_state = "Ready"

        st.caption(f"🤖 **AI Engine Status:** {llm_state}")

    st.markdown("---")

    # 2. Sidebar: Log Input & Configuration Controls
    with st.sidebar:
        st.header("📥 Log Ingestion")

        input_mode = st.radio(
            "Input Mode",
            ["Paste Logs", "Upload File", "Sample Logs"],
            key="input_mode",
        )

        current_log_content = ""

        if input_mode == "Paste Logs":
            pasted = st.text_area(
                "Paste raw log text",
                value=st.session_state.get("input_text", ""),
                height=260,
                placeholder="2026-10-14 10:00:00 [ERROR] app.service: Connection failed...",
                key="pasted_log_area",
            )
            current_log_content = pasted

        elif input_mode == "Upload File":
            uploaded_file = st.file_uploader(
                "Choose a log file (.log, .txt)",
                type=["log", "txt"],
                key="uploaded_log_file",
            )
            if uploaded_file is not None:
                file_bytes = uploaded_file.read()
                try:
                    current_log_content = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    st.error(
                        "❌ Invalid encoding: The uploaded file is not valid UTF-8 text."
                    )
                    current_log_content = ""

        elif input_mode == "Sample Logs":
            sample_choice = st.selectbox(
                "Choose sample fixture",
                [
                    "recurring_failures.log",
                    "sample_application.log",
                    "sample_test_failure.log",
                ],
                key="sample_choice",
            )
            if st.button("Load Selected Sample"):
                current_log_content = _load_sample_log(sample_choice)
                st.session_state["input_text"] = current_log_content
            else:
                current_log_content = st.session_state.get("input_text", "")
                if not current_log_content:
                    current_log_content = _load_sample_log(sample_choice)
                    st.session_state["input_text"] = current_log_content

        # Update input text state
        if current_log_content != st.session_state["input_text"]:
            st.session_state["input_text"] = current_log_content

        # Payload measurement stats
        byte_size = compute_byte_size(current_log_content)
        line_count = compute_line_count(current_log_content)

        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("Lines", f"{line_count:,}")
        with col_stat2:
            st.metric("Size", f"{byte_size:,} B")

        if byte_size > MAX_RECOMMENDED_BYTES:
            st.warning(f"⚠️ Payload ({byte_size:,} B) exceeds recommended 1 MiB limit.")
        if line_count > MAX_RECOMMENDED_LINES:
            st.warning(
                f"⚠️ Line count ({line_count:,}) exceeds recommended 20,000 line limit."
            )

        st.markdown("---")
        st.header("⚙️ Analysis Options")

        include_ai = st.checkbox(
            "Request AI Assistance",
            value=False,
            help=(
                "Requests AI-assisted root-cause hypotheses and triage recommendations with verified citations. "
                "If AI is disabled or fails, deterministic fallback is automatically returned."
            ),
            key="include_ai_toggle",
        )

        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            analyze_clicked = st.button(
                "🚀 Analyze Logs", type="primary", use_container_width=True
            )
        with col_btn2:
            if st.button("Clear", use_container_width=True):
                st.session_state["input_text"] = ""
                st.session_state["active_analysis"] = None
                st.session_state["analyzed_text"] = ""
                st.session_state["_selected_group"] = None
                st.session_state["_selected_occurrence"] = None
                st.session_state["_selected_ai_line"] = None
                st.rerun()

    # 3. Action: Run Analysis when clicked
    if analyze_clicked:
        if not current_log_content or not current_log_content.strip():
            st.warning(
                "⚠️ Please provide log text to analyze (paste, upload, or choose a sample)."
            )
        else:
            with st.spinner(
                "Analyzing log with deterministic parsing & fingerprint grouping..."
            ):
                result_data, error_msg = analyze_logs(
                    log_text=current_log_content,
                    include_ai=include_ai,
                    base_url=get_api_base_url(),
                )

                if error_msg:
                    st.error(f"❌ Analysis Failed:\n\n{error_msg}")
                    st.session_state["active_analysis"] = None
                else:
                    st.session_state["active_analysis"] = result_data
                    st.session_state["analyzed_text"] = current_log_content
                    # Reset selections for new analysis run
                    st.session_state["_selected_group"] = None
                    st.session_state["_selected_occurrence"] = None
                    st.session_state["_selected_ai_line"] = None

    # 4. Display Analysis Results (if available)
    analysis = st.session_state.get("active_analysis")
    analyzed_text = st.session_state.get("analyzed_text", "")

    if analysis:
        # Check if active input differs from analyzed text
        if current_log_content != analyzed_text:
            st.info(
                "ℹ️ **Input has been edited since last analysis.** Click **Analyze Logs** to update results."
            )

        # Header metrics info bar
        status_str = analysis.get("status", "completed")
        duration_ms = analysis.get("processing_time_ms", 0.0)
        request_id = analysis.get("request_id", "")

        col_meta1, col_meta2, col_meta3 = st.columns([2, 2, 3])
        with col_meta1:
            st.markdown(f"**Execution Status:** `{status_str}`")
        with col_meta2:
            st.markdown(f"**Duration:** `{format_duration_ms(duration_ms)}`")
        with col_meta3:
            st.markdown(
                f"**Request ID:** `{request_id[:16]}…`"
                if len(request_id) > 16
                else f"`{request_id}`"
            )

        # 5. Summary Metrics Section
        metrics_data = analysis.get("metrics", {})
        render_metrics(metrics_data)

        st.markdown("---")

        # 6. Tabbed Workspace
        tab_groups, tab_source, tab_ai, tab_warnings = st.tabs(
            [
                "📦 Failure Groups & Stack Traces",
                "📜 Source Line Viewer",
                "🤖 AI Triage & Fallback Insights",
                "⚠️ Parser Warnings",
            ]
        )

        with tab_groups:
            groups_list = analysis.get("failure_groups", [])
            events_list = analysis.get("failure_events", [])
            render_failure_groups(groups_list, events_list)

            # Stack trace viewer for currently selected group
            current_selected_grp = st.session_state.get("_selected_group")
            if current_selected_grp:
                render_stack_traces(events_list, current_selected_grp)

        with tab_source:
            render_source_viewer(
                raw_log_text=analyzed_text,
                selected_group=st.session_state.get("_selected_group"),
                selected_occurrence=st.session_state.get("_selected_occurrence"),
                selected_ai_line=st.session_state.get("_selected_ai_line"),
            )

        with tab_ai:
            render_ai_insights(
                ai_analysis=analysis.get("ai_analysis"),
                analysis_source=analysis.get("analysis_source", "none"),
                status=status_str,
                raw_log_lines_count=metrics_data.get("total_log_lines", 0),
            )

        with tab_warnings:
            warnings_list = analysis.get("parser_warnings", [])
            if warnings_list:
                st.warning(f"⚠️ Encountered {len(warnings_list)} parsing warning(s):")
                for w in warnings_list:
                    st.markdown(f"- {w}")
            else:
                st.success(
                    "✅ Zero parser warnings encountered. All log lines were parsed cleanly."
                )

    elif not analyze_clicked:
        # Initial empty state guidance
        st.info(
            "👋 **Welcome to LogLens AI!**\n\n"
            "To begin inspecting application or test logs:\n"
            "1. Choose an input method from the sidebar (**Paste Logs**, **Upload File**, or **Sample Logs**).\n"
            "2. Optionally enable **Request AI Assistance**.\n"
            "3. Click **🚀 Analyze Logs** to run deterministic parsing, SHA-256 failure clustering, and evidence mapping."
        )


if __name__ == "__main__":
    main()

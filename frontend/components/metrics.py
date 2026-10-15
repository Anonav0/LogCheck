"""Summary metric card rendering for LogLens AI dashboard."""

from __future__ import annotations

import streamlit as st


def render_metrics(metrics: dict) -> None:
    """Render summary metric cards from the analysis response metrics dict.

    Maps directly to the AnalysisMetrics schema returned by the backend.
    Only displays fields that are present; never fabricates zeros for missing fields.
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📄 Total Lines", f"{metrics.get('total_log_lines', 0):,}")
    with col2:
        st.metric(
            "🔴 Failure Events",
            f"{metrics.get('total_failure_events', 0):,}",
        )
    with col3:
        st.metric(
            "📦 Unique Groups",
            f"{metrics.get('unique_failure_groups', 0):,}",
        )
    with col4:
        st.metric(
            "🔁 Repeated Groups",
            f"{metrics.get('repeated_failure_groups', 0):,}",
        )

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("❌ Error Entries", f"{metrics.get('total_error_entries', 0):,}")
    with col6:
        st.metric("⚠️ Warning Entries", f"{metrics.get('total_warning_entries', 0):,}")
    with col7:
        most_freq = metrics.get("most_frequent_failure_count", 0)
        st.metric("📊 Most Frequent", f"{most_freq:,}" if most_freq else "—")
    with col8:
        repeated_events = metrics.get("repeated_failure_events", 0)
        st.metric(
            "🔄 Repeated Events", f"{repeated_events:,}" if repeated_events else "—"
        )

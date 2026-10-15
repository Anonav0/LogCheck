"""Failure group explorer component for LogLens AI dashboard."""

from __future__ import annotations

import streamlit as st


def _severity_badge(level: str | None) -> str:
    """Return an emoji badge for a severity level."""
    if level is None:
        return "⚪"
    level_upper = level.upper()
    if level_upper in ("ERROR", "CRITICAL", "FATAL"):
        return "🔴"
    if level_upper == "WARNING":
        return "🟡"
    if level_upper == "INFO":
        return "🔵"
    return "⚪"


def render_failure_groups(groups: list[dict], failure_events: list[dict]) -> None:
    """Render the failure group explorer with selection and occurrence navigation.

    Args:
        groups: List of FailureGroup dicts from the API response.
        failure_events: List of FailureEvent dicts from the API response.
    """
    if not groups:
        st.info(
            "✅ **No failure groups were detected in this log.**\n\n"
            "This does not guarantee that the application is healthy — "
            "only that no recognized failure patterns were found in the submitted log text."
        )
        return

    st.subheader(f"📦 Failure Groups ({len(groups)})")

    # Sort options
    sort_options = {
        "Most frequent first": lambda g: -g.get("occurrence_count", 0),
        "Earliest occurrence first": lambda g: g.get("first_seen_line", 0),
        "Severity first": lambda g: (
            0
            if (g.get("severity") or "").upper() in ("CRITICAL", "FATAL")
            else 1
            if (g.get("severity") or "").upper() == "ERROR"
            else 2
            if (g.get("severity") or "").upper() == "WARNING"
            else 3
        ),
    }

    sort_by = st.selectbox(
        "Sort groups by",
        list(sort_options.keys()),
        key="group_sort",
    )
    sorted_groups = sorted(groups, key=sort_options[sort_by])

    # Group selector
    group_labels = []
    for g in sorted_groups:
        badge = _severity_badge(g.get("severity"))
        count = g.get("occurrence_count", 1)
        title = g.get("title", "Unknown Failure")
        group_labels.append(f"{badge} [{count}x] {title}")

    selected_idx = st.selectbox(
        "Select a failure group to inspect",
        range(len(sorted_groups)),
        format_func=lambda i: group_labels[i],
        key="selected_group_idx",
    )

    selected_group = sorted_groups[selected_idx]

    # Store selected group in session state for source highlighting
    st.session_state["_selected_group"] = selected_group

    # Group detail card
    with st.container():
        st.markdown(
            f"### {_severity_badge(selected_group.get('severity'))} {selected_group.get('title', 'Unknown')}"
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                f"**Category:** `{selected_group.get('failure_category', '—')}`"
            )
            exc_type = selected_group.get("exception_type")
            if exc_type:
                st.markdown(f"**Exception:** `{exc_type}`")
        with col2:
            st.markdown(f"**Occurrences:** {selected_group.get('occurrence_count', 1)}")
            component = selected_group.get("component")
            if component:
                st.markdown(f"**Component:** `{component}`")
        with col3:
            st.markdown(
                f"**Lines:** {selected_group.get('first_seen_line', '?')} – "
                f"{selected_group.get('last_seen_line', '?')}"
            )
            fp = selected_group.get("fingerprint", "")
            if fp:
                st.markdown(f"**Fingerprint:** `{fp[:12]}…`")

        st.markdown(f"> {selected_group.get('representative_message', '—')}")

    # Occurrence navigator
    occurrences = selected_group.get("occurrences", [])
    if occurrences:
        _render_occurrences(occurrences)


def _render_occurrences(occurrences: list[dict]) -> None:
    """Render occurrence navigator and stack traces for a selected group."""
    st.markdown("---")
    st.markdown(f"#### 🔍 Occurrences ({len(occurrences)})")

    if len(occurrences) > 1:
        occ_labels = [
            f"Occurrence {i + 1} — Line {o.get('primary_line_number', '?')}"
            for i, o in enumerate(occurrences)
        ]
        selected_occ_idx = st.selectbox(
            "Select occurrence",
            range(len(occurrences)),
            format_func=lambda i: occ_labels[i],
            key="selected_occ_idx",
        )
    else:
        selected_occ_idx = 0

    occ = occurrences[selected_occ_idx]
    st.session_state["_selected_occurrence"] = occ

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Event ID:** `{occ.get('event_id', '—')}`")
        st.markdown(
            f"**Lines:** {occ.get('start_line_number', '?')} – "
            f"{occ.get('end_line_number', '?')}"
        )
        ts = occ.get("timestamp")
        if ts:
            st.markdown(f"**Timestamp:** `{ts}`")
    with col2:
        exc_type = occ.get("exception_type")
        if exc_type:
            st.markdown(f"**Exception:** `{exc_type}`")
        level = occ.get("level")
        if level:
            st.markdown(f"**Level:** `{level}`")
        logger = occ.get("logger_name")
        if logger:
            st.markdown(f"**Logger:** `{logger}`")

    st.markdown(f"**Message:** {occ.get('original_message', '—')}")

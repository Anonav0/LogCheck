"""Original source log viewer and evidence highlighting component."""

from __future__ import annotations

import streamlit as st

from frontend.utils import (
    build_source_html,
    split_source_lines,
    validate_line_references,
)


def render_source_viewer(
    raw_log_text: str,
    selected_group: dict | None = None,
    selected_occurrence: dict | None = None,
    selected_ai_line: int | None = None,
) -> None:
    """Render the original source log viewer with interactive highlighting and windowing.

    Args:
        raw_log_text: The canonical raw log text submitted for analysis.
        selected_group: Currently selected failure group dict (if any).
        selected_occurrence: Currently selected failure occurrence dict (if any).
        selected_ai_line: 1-based line number selected from AI insights (if any).
    """
    if not raw_log_text:
        st.info("No log text available for source inspection.")
        return

    lines = split_source_lines(raw_log_text)
    total_lines = len(lines)
    if total_lines == 0:
        st.info("Log is empty.")
        return

    st.subheader(f"📜 Original Source Viewer ({total_lines:,} lines)")

    # Compute highlight sets based on current selections
    primary_lines: set[int] = set()
    context_lines: set[int] = set()
    ai_lines: set[int] = set()

    # AI evidence citation highlight
    if selected_ai_line is not None and 1 <= selected_ai_line <= total_lines:
        ai_lines.add(selected_ai_line)

    # Group and occurrence highlights
    if selected_occurrence:
        prim = selected_occurrence.get("primary_line_number")
        if prim and 1 <= prim <= total_lines:
            primary_lines.add(prim)
        # Add all line numbers of this occurrence as context
        occ_lines = validate_line_references(
            selected_occurrence.get("line_numbers", []), total_lines
        )
        context_lines.update(occ_lines)
    elif selected_group:
        first_line = selected_group.get("first_seen_line")
        if first_line and 1 <= first_line <= total_lines:
            primary_lines.add(first_line)
        grp_lines = validate_line_references(
            selected_group.get("line_numbers", []), total_lines
        )
        context_lines.update(grp_lines)

    # Don't overlap context with primary
    context_lines.difference_update(primary_lines)

    # Navigation & view controls
    col_nav1, col_nav2, col_nav3 = st.columns([2, 2, 3])

    with col_nav1:
        view_mode = st.radio(
            "View Range",
            ["Focused Context (±10 lines)", "Full Log"],
            horizontal=True,
            key="source_view_mode",
        )

    # Determine default focus line
    default_focus = None
    if selected_ai_line:
        default_focus = selected_ai_line
    elif selected_occurrence and selected_occurrence.get("primary_line_number"):
        default_focus = selected_occurrence.get("primary_line_number")
    elif selected_group and selected_group.get("first_seen_line"):
        default_focus = selected_group.get("first_seen_line")

    with col_nav2:
        focus_input = st.number_input(
            "Focus Line Number",
            min_value=1,
            max_value=max(1, total_lines),
            value=default_focus or 1,
            step=1,
            key="source_focus_line",
        )

    with col_nav3:
        # Legend
        st.markdown(
            '<div style="font-size:12px;margin-top:18px;display:flex;gap:12px;align-items:center;">'
            '<span style="display:inline-block;width:12px;height:12px;background:#ff4d4f;border-radius:2px;"></span> Primary Failure'
            '<span style="display:inline-block;width:12px;height:12px;background:#ffa940;border-radius:2px;"></span> Context / Trace'
            '<span style="display:inline-block;width:12px;height:12px;background:#40a9ff;border-radius:2px;"></span> AI Cited'
            "</div>",
            unsafe_allow_html=True,
        )

    # Render HTML source view
    is_focused = view_mode == "Focused Context (±10 lines)"
    html_content = build_source_html(
        lines=lines,
        highlight_primary=primary_lines,
        highlight_context=context_lines,
        highlight_ai=ai_lines,
        focus_line=focus_input if is_focused else None,
        context_radius=10 if is_focused else None,
        max_display_lines=1500,
    )

    st.markdown(html_content, unsafe_allow_html=True)

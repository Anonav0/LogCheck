"""Stack trace inspection component for LogLens AI dashboard."""

from __future__ import annotations

import streamlit as st


def render_stack_traces(
    failure_events: list[dict],
    selected_group: dict | None = None,
) -> None:
    """Render stack traces for the selected failure group's events.

    Args:
        failure_events: All FailureEvent dicts from the API response.
        selected_group: Currently selected FailureGroup dict (if any).
    """
    if selected_group is None:
        return

    # Find failure events that match this group's occurrences
    occ_event_ids = {o.get("event_id") for o in selected_group.get("occurrences", [])}

    relevant_events = [e for e in failure_events if e.get("event_id") in occ_event_ids]

    if not relevant_events:
        return

    st.markdown("#### 📜 Stack Traces")

    for event in relevant_events:
        stack = event.get("stack_trace", [])
        if not stack:
            continue

        event_id = event.get("event_id", "?")
        primary_line = event.get("primary_line_number", "?")
        exc_type = event.get("exception_type", "")
        message = event.get("message", "")

        header = f"Event `{event_id}` — Line {primary_line}"
        if exc_type:
            header += f" — `{exc_type}`"

        with st.expander(header, expanded=len(relevant_events) == 1):
            if message:
                st.markdown(f"**Message:** {message}")

            # Display stack trace in a code block to preserve formatting
            trace_text = "\n".join(stack)
            st.code(trace_text, language="python", line_numbers=False)

            line_range = event.get("line_numbers", [])
            if line_range:
                st.caption(
                    f"Source lines: {min(line_range)} – {max(line_range)} "
                    f"({len(line_range)} lines)"
                )

"""Display formatting, safe HTML rendering, and UI utility helpers for LogLens AI."""

from __future__ import annotations

import html


def escape_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS when rendering untrusted log text."""
    if not text:
        return ""
    return html.escape(text, quote=True)


def format_line_number(n: int, total_lines: int) -> str:
    """Format a 1-based line number with consistent width padding."""
    width = max(len(str(total_lines)), 3)
    return f"{n:>{width}}"


def split_source_lines(raw_text: str) -> list[str]:
    """Split raw log text into canonical source lines matching backend semantics.

    Preserves blank lines and avoids trailing line break characters.
    """
    if not raw_text:
        return []
    return raw_text.splitlines()


def compute_byte_size(text: str) -> int:
    """Compute the total UTF-8 encoded byte size of a text string."""
    if not text:
        return 0
    return len(text.encode("utf-8", errors="replace"))


def compute_line_count(text: str) -> int:
    """Return the physical line count of a log text."""
    return len(split_source_lines(text))


def format_duration_ms(ms: float) -> str:
    """Format processing duration in milliseconds into a readable string."""
    if ms < 0:
        return "0.00 ms"
    if ms < 1000.0:
        return f"{ms:.2f} ms"
    return f"{ms / 1000.0:.2f} s"


def format_fingerprint(fp: str, max_len: int = 12) -> str:
    """Format a SHA-256 fingerprint hash for UI display."""
    if not fp:
        return "—"
    if len(fp) > max_len:
        return f"{fp[:max_len]}…"
    return fp


def severity_color(level: str | None) -> str:
    """Return an accessible CSS hex color corresponding to severity level."""
    if not level:
        return "#495057"
    normalized = level.strip().upper()
    if normalized in ("CRITICAL", "FATAL", "ERROR"):
        return "#d90429"
    if normalized in ("WARN", "WARNING"):
        return "#e85d04"
    if normalized == "INFO":
        return "#0077b6"
    if normalized in ("DEBUG", "TRACE"):
        return "#6c757d"
    return "#495057"


def validate_line_references(line_numbers: list[int], total_lines: int) -> list[int]:
    """Filter and sort 1-based line references to only valid lines within source bounds."""
    if total_lines <= 0 or not line_numbers:
        return []
    valid = {int(ln) for ln in line_numbers if 1 <= int(ln) <= total_lines}
    return sorted(valid)


def build_source_html(
    lines: list[str],
    highlight_primary: set[int] | None = None,
    highlight_context: set[int] | None = None,
    highlight_ai: set[int] | None = None,
    focus_line: int | None = None,
    context_radius: int | None = None,
    max_display_lines: int = 1000,
) -> str:
    """Build an accessible, safely escaped HTML document for viewing source lines with highlights.

    Args:
        lines: List of canonical source lines (0-indexed list representing 1-based lines).
        highlight_primary: 1-based line numbers for primary error / exception lines.
        highlight_context: 1-based line numbers for stack trace / occurrence lines.
        highlight_ai: 1-based line numbers for validated AI evidence citations.
        focus_line: Optional 1-based line number to center context around.
        context_radius: Optional window radius around focus_line. None shows all lines.
        max_display_lines: Maximum lines to render to protect browser performance.

    Returns:
        Renderable HTML string with strictly escaped content and line styles.
    """
    total = len(lines)
    if total == 0:
        return '<div style="font-family:monospace;padding:12px;color:#888;">No log lines available.</div>'

    primary_set = highlight_primary or set()
    context_set = highlight_context or set()
    ai_set = highlight_ai or set()

    # Determine display window
    if focus_line is not None and context_radius is not None:
        start_idx = max(0, focus_line - 1 - context_radius)
        end_idx = min(total, focus_line + context_radius)
    else:
        start_idx = 0
        end_idx = min(total, max_display_lines)

    width = max(len(str(total)), 3)
    html_lines: list[str] = []

    # Container style
    html_lines.append(
        '<div style="'
        "font-family: 'JetBrains Mono', Consolas, Monaco, monospace; "
        "font-size: 13px; "
        "line-height: 1.5; "
        "background-color: #1e1e1e; "
        "color: #d4d4d4; "
        "padding: 10px; "
        "border-radius: 6px; "
        "overflow-x: auto; "
        "max-height: 520px; "
        "overflow-y: auto; "
        "border: 1px solid #333;"
        '">'
    )

    if start_idx > 0:
        html_lines.append(
            f'<div style="color: #888; padding: 4px 8px; font-style: italic;">'
            f"… {start_idx} earlier lines not shown in this context window …</div>"
        )

    for idx in range(start_idx, end_idx):
        line_num = idx + 1
        raw_text = lines[idx]
        escaped_content = escape_html(raw_text)
        if not escaped_content:
            escaped_content = "&nbsp;"

        # Highlighting priority: Primary > Context > AI > Normal
        is_primary = line_num in primary_set
        is_context = line_num in context_set
        is_ai = line_num in ai_set
        is_focus = line_num == focus_line

        line_style = "display: flex; white-space: pre; margin: 0; padding: 1px 4px; "
        num_style = f"color: #717171; user-select: none; margin-right: 12px; min-width: {width}ch; text-align: right; "

        if is_primary:
            line_style += "background-color: rgba(230, 57, 70, 0.28); border-left: 3px solid #ff4d4f; "
            num_style += "color: #ff7875; font-weight: bold; "
        elif is_ai:
            line_style += "background-color: rgba(0, 150, 255, 0.22); border-left: 3px solid #40a9ff; "
            num_style += "color: #69c0ff; font-weight: bold; "
        elif is_context:
            line_style += "background-color: rgba(244, 162, 97, 0.20); border-left: 3px solid #ffa940; "
            num_style += "color: #ffc069; "
        elif is_focus:
            line_style += "border-left: 3px solid #52c41a; "

        html_lines.append(
            f'<div style="{line_style}">'
            f'<span style="{num_style}">{line_num:>{width}}</span>'
            f'<span style="flex-grow: 1;">{escaped_content}</span>'
            f"</div>"
        )

    if end_idx < total:
        remaining = total - end_idx
        html_lines.append(
            f'<div style="color: #888; padding: 4px 8px; font-style: italic;">'
            f"… {remaining} subsequent lines not shown (full log has {total:,} lines) …</div>"
        )

    html_lines.append("</div>")
    return "\n".join(html_lines)

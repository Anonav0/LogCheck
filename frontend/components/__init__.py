"""Dashboard UI components package."""

from frontend.components.ai_insights import render_ai_insights
from frontend.components.failure_groups import render_failure_groups
from frontend.components.metrics import render_metrics
from frontend.components.source_viewer import render_source_viewer
from frontend.components.stack_trace import render_stack_traces

__all__ = [
    "render_ai_insights",
    "render_failure_groups",
    "render_metrics",
    "render_source_viewer",
    "render_stack_traces",
]

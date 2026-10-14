"""Application entry point for LogLens AI.

This module provides the baseline entry point and package identity for LogLens AI.
In Phase 1, project scaffolding, configuration, and sample log fixtures are established.
FastAPI routes, log parsing, failure detection, and LLM integrations will be implemented
in subsequent phases.
"""

from app.core.config import Settings, get_settings


def get_app_info() -> dict[str, str | bool]:
    """Return basic application metadata and configuration state."""
    settings: Settings = get_settings()
    return {
        "app_name": settings.APP_NAME,
        "app_env": settings.APP_ENV,
        "debug": settings.DEBUG,
        "llm_enabled": settings.LLM_ENABLED,
        "status": "scaffolding_ready",
    }


if __name__ == "__main__":
    info = get_app_info()
    print(
        f"Initialized {info['app_name']} ({info['app_env']}) - Status: {info['status']}"
    )

"""FastAPI dependency injection utilities."""

from app.core.config import Settings, get_settings


def get_app_settings() -> Settings:
    """Provide current application settings to route handlers."""
    return get_settings()


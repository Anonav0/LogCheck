"""Pytest configuration and shared fixtures for LogLens AI."""

from collections.abc import Generator
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the absolute path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def load_fixture() -> Generator:
    """Return a helper function that reads a fixture file as UTF-8 text."""

    def _loader(filename: str) -> str:
        filepath = FIXTURES_DIR / filename
        return filepath.read_text(encoding="utf-8")

    yield _loader


@pytest.fixture
def sample_application_log_path() -> Path:
    """Return path to sample_application.log."""
    return FIXTURES_DIR / "sample_application.log"


@pytest.fixture
def sample_application_log_text(sample_application_log_path: Path) -> str:
    """Return content of sample_application.log."""
    return sample_application_log_path.read_text(encoding="utf-8")


@pytest.fixture
def sample_test_failure_log_path() -> Path:
    """Return path to sample_test_failure.log."""
    return FIXTURES_DIR / "sample_test_failure.log"


@pytest.fixture
def sample_test_failure_log_text(sample_test_failure_log_path: Path) -> str:
    """Return content of sample_test_failure.log."""
    return sample_test_failure_log_path.read_text(encoding="utf-8")


@pytest.fixture
def recurring_failures_log_path() -> Path:
    """Return path to recurring_failures.log."""
    return FIXTURES_DIR / "recurring_failures.log"


@pytest.fixture
def recurring_failures_log_text(recurring_failures_log_path: Path) -> str:
    """Return content of recurring_failures.log."""
    return recurring_failures_log_path.read_text(encoding="utf-8")


@pytest.fixture
def malformed_log_path() -> Path:
    """Return path to malformed.log."""
    return FIXTURES_DIR / "malformed.log"


@pytest.fixture
def malformed_log_text(malformed_log_path: Path) -> str:
    """Return content of malformed.log."""
    return malformed_log_path.read_text(encoding="utf-8")


@pytest.fixture
def clean_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return a clean Settings instance with defaults, isolated from local .env."""
    get_settings.cache_clear()
    # Ensure no external LLM variables leak into default settings
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("MAX_LOG_SIZE_BYTES", raising=False)
    monkeypatch.delenv("MAX_LOG_LINES", raising=False)
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("LLM_MAX_FAILURE_GROUPS", raising=False)
    monkeypatch.delenv("LLM_MAX_EVIDENCE_LINES", raising=False)
    monkeypatch.delenv("LLM_MAX_PROMPT_CHARS", raising=False)

    settings = Settings(_env_file=None)
    yield settings
    get_settings.cache_clear()


@pytest.fixture
def api_client(clean_settings: Settings) -> Generator:
    """Return an ASGI test client for the FastAPI application with clean settings."""
    from app.main import create_app
    from tests.asgi_client import ASGIClient

    app = create_app(settings=clean_settings)
    yield ASGIClient(app)

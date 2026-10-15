"""Health and readiness probe routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_app_settings
from app.api.schemas.responses import HealthResponse, ReadyResponse
from app.core.config import Settings

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Liveness Probe",
    description="Reports whether the LogLens AI API process is operational and receiving traffic.",
)
async def get_health() -> HealthResponse:
    """Return process liveness confirmation without calling external services."""
    return HealthResponse(status="ok", service="LogLens AI")


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Service Readiness Probe",
    description="Reports whether the deterministic pipeline and optional LLM provider are ready for analysis.",
)
async def get_readiness(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ReadyResponse:
    """Return application readiness status and offline LLM availability state.

    The deterministic pipeline operates independently of LLM availability.
    LLM availability is evaluated strictly against server configuration without
    initiating external network calls.
    """
    llm_available = False
    if settings.LLM_ENABLED:
        provider = (settings.LLM_PROVIDER or "").strip().lower()
        if provider == "mock":
            llm_available = True
        elif provider in (
            "openai",
            "azure_openai",
            "google",
            "gemini",
            "google_gemini",
            "google-gemini",
        ):
            llm_available = bool(settings.LLM_API_KEY and settings.LLM_API_KEY.strip())

    return ReadyResponse(
        status="ready",
        llm_enabled=settings.LLM_ENABLED,
        llm_available=llm_available,
    )

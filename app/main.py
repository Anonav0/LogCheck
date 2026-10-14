"""Application entry point and FastAPI application factory for LogLens AI.

Configures application metadata, request correlation middleware, centralized
exception handlers, and route registration for health and log analysis.
"""

import re
import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import (
    evidence_integrity_error_handler,
    global_exception_handler,
    http_exception_handler,
    input_validation_error_handler,
    request_validation_error_handler,
)
from app.api.routes import analysis_router, health_router
from app.core.config import Settings, get_settings
from app.core.exceptions import EvidenceIntegrityError, InputValidationError

_VALID_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    cfg = settings or get_settings()

    app = FastAPI(
        title="LogLens AI API",
        description=(
            "Intelligent log analysis API combining deterministic failure detection, "
            "canonical source line mapping, SHA-256 failure fingerprinting, and "
            "optional AI-assisted debugging triage with verified evidence references."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "Health",
                "description": "Liveness and readiness probes for operational monitoring.",
            },
            {
                "name": "Analysis",
                "description": "Deterministic and AI-assisted log analysis pipeline.",
            },
        ],
    )

    # Restrictive CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if cfg.DEBUG else ["http://localhost", "http://127.0.0.1"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Request correlation and timing middleware
    @app.middleware("http")
    async def request_correlation_middleware(
        request: Request, call_next: Callable
    ) -> Response:
        start_time = time.perf_counter()

        client_request_id = request.headers.get("X-Request-ID")
        if client_request_id and _VALID_REQUEST_ID_REGEX.match(client_request_id):
            request_id = client_request_id
        else:
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception as exc:
            response = await global_exception_handler(request, exc)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

        return response

    # Centralized exception handlers
    app.add_exception_handler(InputValidationError, input_validation_error_handler)
    app.add_exception_handler(EvidenceIntegrityError, evidence_integrity_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    # Router registration
    app.include_router(health_router)
    app.include_router(analysis_router)

    if settings is not None:
        from app.api.dependencies import get_app_settings

        app.dependency_overrides[get_app_settings] = lambda: cfg

    return app


# Default application instance for Uvicorn (uvicorn app.main:app)
app = create_app()


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

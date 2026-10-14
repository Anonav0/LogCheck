"""LLM integration package for LogLens AI."""

from app.services.llm.analysis_service import (
    analyze_failures_with_ai,
    verify_ai_evidence,
)
from app.services.llm.base import LLMProvider
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMEvidenceVerificationError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMResponseError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.llm.fallback import build_deterministic_fallback
from app.services.llm.prompt_builder import (
    BuiltPrompt,
    PromptEvidenceLine,
    build_analysis_prompt,
    redact_sensitive_content,
)
from app.services.llm.provider_factory import (
    MockLLMProvider,
    OpenAIProvider,
    get_llm_provider,
)
from app.services.llm.schemas import (
    AIAnalysis,
    AIAnalysisResult,
    EvidenceReference,
    LikelyCause,
    RecommendedAction,
)

__all__ = [
    "AIAnalysis",
    "AIAnalysisResult",
    "BuiltPrompt",
    "EvidenceReference",
    "LLMAuthenticationError",
    "LLMConfigurationError",
    "LLMError",
    "LLMEvidenceVerificationError",
    "LLMNetworkError",
    "LLMProvider",
    "LLMRateLimitError",
    "LLMResponseError",
    "LLMResponseValidationError",
    "LLMTimeoutError",
    "LikelyCause",
    "MockLLMProvider",
    "OpenAIProvider",
    "PromptEvidenceLine",
    "RecommendedAction",
    "analyze_failures_with_ai",
    "build_analysis_prompt",
    "build_deterministic_fallback",
    "get_llm_provider",
    "redact_sensitive_content",
    "verify_ai_evidence",
]


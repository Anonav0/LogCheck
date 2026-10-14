"""Service layer for LogLens AI."""

from app.services.evidence_validator import (
    run_validated_analysis,
    validate_analysis_result,
    validate_parsing_result,
)
from app.services.exception_detector import (
    detect_assertion_failure,
    detect_java_exception,
    detect_python_exception,
    detect_test_failure_indicator,
)
from app.services.fingerprinting import (
    FailureSignature,
    extract_failure_signature,
    generate_fingerprint,
    normalize_failure_message,
    serialize_signature,
)
from app.services.grouping import (
    analyze_failures,
    compute_analysis_metrics,
    group_failures,
)
from app.services.input_validator import (
    validate_log_file_bytes,
    validate_log_input,
)
from app.services.llm import (
    AIAnalysis,
    AIAnalysisResult,
    EvidenceReference,
    LikelyCause,
    MockLLMProvider,
    OpenAIProvider,
    RecommendedAction,
    analyze_failures_with_ai,
    build_deterministic_fallback,
    get_llm_provider,
)
from app.services.log_parser import LogParser, parse_log_text
from app.services.stack_trace_parser import (
    is_java_caused_by,
    is_java_stack_frame,
    is_python_chaining_marker,
    is_python_stack_frame,
    is_python_traceback_header,
    is_stack_frame_line,
)

__all__ = [
    "AIAnalysis",
    "AIAnalysisResult",
    "EvidenceReference",
    "FailureSignature",
    "LikelyCause",
    "LogParser",
    "MockLLMProvider",
    "OpenAIProvider",
    "RecommendedAction",
    "analyze_failures",
    "analyze_failures_with_ai",
    "build_deterministic_fallback",
    "compute_analysis_metrics",
    "detect_assertion_failure",
    "detect_java_exception",
    "detect_python_exception",
    "detect_test_failure_indicator",
    "extract_failure_signature",
    "generate_fingerprint",
    "get_llm_provider",
    "group_failures",
    "is_java_caused_by",
    "is_java_stack_frame",
    "is_python_chaining_marker",
    "is_python_stack_frame",
    "is_python_traceback_header",
    "is_stack_frame_line",
    "normalize_failure_message",
    "parse_log_text",
    "run_validated_analysis",
    "serialize_signature",
    "validate_analysis_result",
    "validate_log_file_bytes",
    "validate_log_input",
    "validate_parsing_result",
]

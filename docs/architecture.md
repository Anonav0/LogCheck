# Architecture & System Design — LogLens AI

LogLens AI is designed around a **deterministic-first, evidence-anchored architecture**. The system strictly decouples deterministic log ingestion, parsing, and failure clustering from optional LLM-assisted triage. This design ensures that core observability and incident diagnostics remain completely functional, fast, and reliable even when external AI providers are offline, rate-limited, or unconfigured.

---

## 1. System Pipeline Architecture

```mermaid
flowchart TD
    subgraph ClientLayer["Client & Presentation Layer"]
        User(["Developer / SRE"])
        StreamlitUI["Streamlit Dashboard\n(frontend/streamlit_app.py)"]
        CurlCLI["CLI / CI / curl\n(HTTP Clients)"]
    end

    subgraph APILayer["FastAPI Interface Layer (app/main.py)"]
        CorrelationMW["Correlation & Timing Middleware\n(X-Request-ID, X-Process-Time)"]
        HealthRouter["Health & Readiness Probes\n(GET /health, GET /health/ready)"]
        AnalyzeRouter["Analysis Endpoint\n(POST /api/v1/analyze)"]
        ErrorHandlers["Standardized Error Envelopes\n(app/api/errors.py)"]
    end

    subgraph IngestionBoundary["Ingestion & Boundary Protection"]
        InputVal["Input Validator\n(app/services/input_validator.py)\n• Byte limit (1 MiB)\n• Line count limit (20k)\n• Line length limit (16k)\n• UTF-8 encoding guard"]
    end

    subgraph DeterministicCore["Deterministic Processing Core"]
        LogParser["Canonical Multiline Parser\n(app/services/log_parser.py)\n• 1-based indexing\n• Timestamp & level extraction\n• Python & Java stack-trace parsing"]
        ExceptDetect["Exception Detector\n(app/services/exception_detector.py)\n• Failure event extraction\n• Exception classification"]
        Fingerprinter["Failure Fingerprinter\n(app/services/fingerprinting.py)\n• Volatile token normalization (UUIDs, IPs, mem addrs)\n• Canonical SHA-256 generation"]
        Grouper["Failure Grouper & Metrics\n(app/services/grouping.py)\n• Recurrence grouping\n• Occurrence tracking\n• Frequency metrics"]
        EvidenceValidator["Evidence Validator\n(app/services/evidence_validator.py)\n• Source line text matching\n• Entity reference validation\n• Invariant integrity checks"]
    end

    subgraph LLMOrchestration["AI Triage & Fallback Subsystem"]
        PromptBuilder["Prompt Construction & Redaction\n(app/services/llm/prompt_builder.py)\n• Token & secret redaction\n• Untrusted data sandboxing (<LOG_EVIDENCE>)\n• Character limit truncation"]
        ProviderFactory["Provider Abstraction Layer\n(app/services/llm/provider_factory.py)\n• Mock, Google Gemini, OpenAI"]
        ExternalLLM[("External LLM Provider\n(Gemini / OpenAI API)")]
        SchemaValidator["Pydantic Response Validator\n(app/services/llm/schemas.py)\n• AIAnalysis schema compliance\n• Confidence & priority validation"]
        EvidenceChecker["AI Citation Verification\n(app/services/llm/analysis_service.py)\n• 1-based line bounds check\n• Excerpt content matching\n• Event & fingerprint verification"]
        DeterministicFallback["Deterministic Fallback Engine\n(app/services/llm/fallback.py)\n• Provable fallback report\n• Clean provenance & reason"]
    end

    %% Interactions
    User --> StreamlitUI
    User --> CurlCLI
    StreamlitUI -->|HTTP| CorrelationMW
    CurlCLI -->|HTTP| CorrelationMW

    CorrelationMW --> HealthRouter
    CorrelationMW --> AnalyzeRouter
    CorrelationMW -.-> ErrorHandlers

    AnalyzeRouter --> InputVal
    InputVal -->|Validated Input| LogParser
    InputVal -- Rejection (413/422) --> ErrorHandlers

    LogParser --> ExceptDetect
    ExceptDetect --> Fingerprinter
    Fingerprinter --> Grouper
    Grouper --> EvidenceValidator

    EvidenceValidator -->|include_ai = false| FinalResponse["Structured AnalyzeLogResponse"]
    EvidenceValidator -->|include_ai = true & LLM_ENABLED = true| PromptBuilder
    EvidenceValidator -->|include_ai = true & LLM_ENABLED = false| DeterministicFallback

    PromptBuilder --> ProviderFactory
    ProviderFactory -->|Bounded HTTPS Request| ExternalLLM
    ExternalLLM -->|JSON Response| SchemaValidator

    ProviderFactory -.->|Timeout / Network Drop / 429| DeterministicFallback
    SchemaValidator -.->|Invalid JSON / Schema Error| DeterministicFallback

    SchemaValidator -->|Valid Schema| EvidenceChecker
    EvidenceChecker -->|Verified Citations| FinalResponse
    EvidenceChecker -.->|Hallucinated Evidence Rejected| DeterministicFallback

    DeterministicFallback --> FinalResponse
    FinalResponse --> AnalyzeRouter
    AnalyzeRouter --> StreamlitUI
```

---

## 2. Core Architectural Pillars

### 1. Pre-Parse Boundary Protection

Untrusted logs enter through `app/services/input_validator.py` before hitting parsing routines:

- **Maximum Payload Size:** Strict 1 MiB boundary (`1,048,576` bytes). Payloads $\ge$ 1,048,577 bytes are rejected immediately with HTTP 413 `LOG_TOO_LARGE`.
- **Maximum Line Count:** Upper limit of 20,000 lines. Oversized logs are rejected with HTTP 413 `TOO_MANY_LOG_LINES`.
- **Maximum Line Length:** Upper limit of 16,384 characters per single line to avoid regex catastrophic backtracking (`LOG_LINE_TOO_LONG`).
- **Encoding Integrity:** Strictly rejects non-UTF-8 binary bytes with HTTP 422 `INVALID_ENCODING`.

### 2. Canonical 1-Based Line Indexing

To prevent off-by-one errors common in log parsers:

- Lines are split using universal newline rules (`splitlines()`), preserving empty lines and whitespace.
- Every parsed entry, failure event, stack frame, and AI citation maps to an immutable, 1-based source line index `[1, total_lines]`.

### 3. Volatile Token Normalization & SHA-256 Fingerprinting

To cluster identical root causes that manifest with variable diagnostic tokens:

- **Normalization:** Regex replacement filters out hex memory addresses (`0x7f8b9c0012a0`), UUIDs (`550e8400-e29b-41d4-a716-446655440000`), IPv4 addresses (`192.168.1.100`), thread IDs, and numeric request IDs.
- **Hashing:** A canonical string composed of `exception_type`, `normalized_message`, `top_stack_frame`, and `component` is hashed with SHA-256, generating a stable 64-character fingerprint.
- **Ordering:** Groups are stably sorted by `occurrence_count` descending, then `first_seen_line` ascending.

### 4. Evidence Integrity Verification

Before results leave the core, `app/services/evidence_validator.py` validates that:

- Every line number referenced actually exists in the source text.
- Every referenced excerpt matches the literal slice of that line.
- Aggregate metrics agree with underlying failure counts and group occurrences.

### 5. Sandboxed AI Triage & Deterministic Fallback

When AI analysis is requested (`include_ai: true`):

1. **Prompt Isolation:** Raw log lines are wrapped in `<LOG_EVIDENCE>` tags with strict system instructions treating logs as inert, untrusted diagnostic data.
2. **Secret Redaction:** API keys, Bearer tokens, passwords, and private key blocks are redacted prior to model dispatch.
3. **Citation Verification:** Every line number and excerpt cited by the LLM is checked against the raw log. Hallucinated lines trigger an immediate fallback.
4. **Deterministic Fallback:** If the LLM provider times out, drops connection, returns malformed JSON, violates the Pydantic schema, or cites hallucinated lines, LogLens AI automatically synthesizes a deterministic fallback report derived from the grouped failures, ensuring zero downtime.

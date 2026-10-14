# LogLens AI — AI-Assisted Application Log Analyzer

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/tested_with-pytest-0a9edc.svg)](https://docs.pytest.org/)

**LogLens AI** is an intelligent log analysis engine designed to help software engineers rapidly inspect application and test logs, isolate errors and exceptions, extract multiline stack traces, group recurring failures via deterministic fingerprinting, and generate actionable, evidence-backed debugging summaries using LLMs.

> [!NOTE]
> **Development Status: Phase 5 Completed (LLM Integration & AI Triage Layer)**
> A provider-independent LLM service with strict Pydantic response validation, bounded prompt construction, conservative secret redaction, post-generation source-evidence verification, and deterministic offline fallback is fully implemented and tested. FastAPI REST endpoints and Streamlit dashboard will be built in Phase 6.

---

## 1. Problem Statement

Modern software applications and automated test suites generate verbose, noisy logs. When incidents or test suite failures occur:
- Developers must manually sift through thousands of lines to spot relevant errors.
- Raw log inputs can be corrupted, oversized, or contain malicious line lengths designed to cause denial of service.
- Discrepancies between log splitters and parsers cause "off-by-one" line numbering errors.
- Generic LLM summaries often hallucinate nonexistent line numbers, invent ungrounded root causes, or expose credentials sent in raw prompts.

**LogLens AI** addresses these challenges through a strict 4-tier safety architecture:
1. **Pre-Parse Input Validation:** Rejects empty, invalidly encoded, or oversized payloads before parsing begins.
2. **Deterministic Processing Pipeline:** Parses lines, preserves exact 1-based source line numbers, extracts complete stack traces, and fingerprints failures deterministically into recurring failure groups.
3. **Evidence Integrity Verification:** Verifies every line reference, raw line text, group occurrence mapping, and aggregate metric against the original source log.
4. **Evidence-Anchored AI Triage:** Sends bounded, structured summaries to an LLM to generate root-cause hypotheses and investigation steps, strictly validating every returned line reference against original source logs with instant deterministic fallback upon any provider failure.

---

## 2. LLM Integration Architecture (Phase 5)

The AI triage layer converts deterministic failure groups into structured, actionable debugging summaries while guaranteeing evidence integrity:

```
[ FailureAnalysisResult ] ────────────┐
                                      ▼
                      [ Step 1: Prompt Builder ]
                      - Bounded group & line selection (LLM_MAX_FAILURE_GROUPS, LLM_MAX_EVIDENCE_LINES)
                      - Conservative secret redaction (API keys, bearer tokens, passwords)
                      - Untrusted log content serialized into <LOG_EVIDENCE> JSON block
                                      │
                                      ▼
                      [ Step 2: Provider Invocation ]
                      - Bounded request timeout (LLM_TIMEOUT_SECONDS)
                      - Standardized LLMProvider interface (MockLLMProvider, OpenAIProvider)
                                      │
                      ┌───────────────┴───────────────┐
                      │ On Success                    │ On Timeout / Auth / Network / RateLimit
                      ▼                               ▼
        [ Step 3: Pydantic Validation ]     [ Step 5: Deterministic Fallback ]
        - Validates AIAnalysis schema       - Derives insights from grouping metrics
        - Forbids unknown fields            - Emits verified first-seen references
        - Enforces confidence & bounds      - Marks analysis_source="fallback"
                      │
                      ▼
        [ Step 4: Evidence Verification ]
        - Verifies cited lines exist (1..N)
        - Verifies excerpts match source lines
        - Verifies event IDs & fingerprints
                      │
          ┌───────────┴───────────┐
          │ Pass                  │ Fail
          ▼                       ▼
   [ AIAnalysisResult ]    [ Deterministic Fallback ]
   analysis_source="llm"   analysis_source="fallback"
```

### Supported Providers & Factory
The architecture decouples the core application from specific AI vendors via the `LLMProvider` interface:
- **`MockLLMProvider`:** Fully offline, deterministic mock provider for testing and environments without external network access. Supports custom response injection, latency simulation, and error injection.
- **`OpenAIProvider`:** Production provider adapter calling the OpenAI Chat Completions API with structured JSON responses (`gpt-4o-mini`, `gpt-4o`). Translates HTTP status codes (401, 403, 429, 5xx) to provider-independent exceptions without exposing credentials.
- **Extensible Factory:** `get_llm_provider(settings)` resolves the active provider from configuration.

### Configurable LLM Settings

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_ENABLED` | `bool` | `False` | Master switch for LLM requests. When `False`, returns deterministic fallback immediately. |
| `LLM_PROVIDER` | `str \| None` | `None` | Provider identifier: `'mock'` or `'openai'`. |
| `LLM_API_KEY` | `str \| None` | `None` | Provider secret key (never required for offline operation or tests). |
| `LLM_MODEL` | `str \| None` | `'gpt-4o-mini'` | Model identifier. |
| `LLM_TIMEOUT_SECONDS` | `float` | `30.0` | Strict timeout ceiling for provider network requests. |
| `LLM_MAX_OUTPUT_TOKENS` | `int` | `1200` | Maximum token limit for model response. |
| `LLM_MAX_FAILURE_GROUPS`| `int` | `10` | Maximum failure groups included in model prompt (sorted by recurrence). |
| `LLM_MAX_EVIDENCE_LINES`| `int` | `80` | Maximum evidence lines included in prompt. |
| `LLM_MAX_PROMPT_CHARS`  | `int` | `30000` | Maximum character limit for constructed prompt. |

---

## 3. Strict Pydantic Response Schemas

All model responses must conform to `AIAnalysis` (`extra="forbid"`):

```python
class EvidenceReference(BaseModel):
    line_number: int  # ge=1, le=1_000_000
    excerpt: str  # min_length=1, max_length=2000
    failure_event_id: str | None = None
    fingerprint: str | None = None


class LikelyCause(BaseModel):
    description: str
    reasoning: str
    evidence_refs: list[EvidenceReference]


class RecommendedAction(BaseModel):
    action: str
    rationale: str
    priority: Literal["high", "medium", "low"]
    evidence_refs: list[EvidenceReference]


class AIAnalysis(BaseModel):
    summary: str
    likely_causes: list[LikelyCause]
    recommended_actions: list[RecommendedAction]
    confidence: float  # ge=0.0, le=1.0
    limitations: list[str]
    evidence_refs: list[EvidenceReference]
```

---

## 4. Source Evidence Verification Policy

AI-generated references are untrusted until verified:
1. **Line Number Range:** $1 \le \text{line\_number} \le \text{total\_lines}$.
2. **Excerpt Content:** Must faithfully match the source log line (or its model-visible redacted representation).
3. **Entity Links:** Any cited `failure_event_id` or `fingerprint` must exist in the deterministic analysis.
4. **Integrity Interception:** If any reference is invalid or hallucinated, the analysis is rejected and deterministic fallback is invoked with reason `"EVIDENCE_VERIFICATION_FAILED"`.

---

## 5. Privacy & Secret Redaction

Prompt building applies conservative regex redaction before sending excerpts to an external LLM:
- **API Keys:** `sk-[a-zA-Z0-9_-]{20,}` $\rightarrow$ `[REDACTED_API_KEY]`
- **Bearer Tokens:** `Bearer [a-zA-Z0-9_\-\.]{20,}` $\rightarrow$ `Bearer [REDACTED_TOKEN]`
- **Passwords / Secrets:** `password="xyz"`, `secret="xyz"` $\rightarrow$ `password="[REDACTED]"`
- **Private Keys:** PEM private key blocks $\rightarrow$ `[REDACTED_PRIVATE_KEY]`

> [!IMPORTANT]
> Redaction is a defense-in-depth measure. Full raw prompts and raw responses are never logged in application logs or exception traces.

---

## 6. Programmatic Usage Examples

### Running AI Analysis with Mock Provider (Offline)
```python
from pathlib import Path
from app.core.config import Settings
from app.services.grouping import analyze_failures
from app.services.llm import MockLLMProvider, analyze_failures_with_ai
from app.services.log_parser import parse_log_text

log_text = Path("tests/fixtures/recurring_failures.log").read_text(encoding="utf-8")
analysis = analyze_failures(parse_log_text(log_text))

settings = Settings(LLM_ENABLED=True, LLM_PROVIDER="mock", _env_file=None)
ai_result = analyze_failures_with_ai(
    analysis_result=analysis,
    raw_log=log_text,
    settings=settings,
)

print(f"Source: {ai_result.analysis_source}")  # 'llm'
print(f"Summary: {ai_result.analysis.summary}")
print(f"Confidence: {ai_result.analysis.confidence}")
print(f"Verified Citations: {ai_result.verified_evidence_count}")
```

### Deterministic Fallback Output (When LLM is Disabled or Fails)
```python
settings = Settings(LLM_ENABLED=False, _env_file=None)
ai_result = analyze_failures_with_ai(
    analysis_result=analysis, raw_log=log_text, settings=settings
)

print(f"Source: {ai_result.analysis_source}")  # 'fallback'
print(f"Reason: {ai_result.fallback_reason}")  # 'LLM_DISABLED'
print(
    f"Summary: {ai_result.analysis.summary}"
)  # 'Deterministic failure analysis identified 4 failure event(s)...'
```

---

## 7. Known Limitations

- **Hypotheses vs. Proof:** Model-generated root causes are structured hypotheses, not confirmed diagnoses. Developers should review cited evidence lines before taking disruptive actions.
- **Redaction Coverage:** Automated regex redaction catches common credential formats; proprietary tokens or unusual formats may require manual sanitization before submission.

---

## 8. Technology Stack

- **Core & Runtime:** Python 3.11+, Pydantic v2, Pydantic-Settings, python-dotenv
- **HTTP Transport:** requests
- **Testing:** pytest, pytest-cov (245 passing tests, 91% code coverage)
- **Linting & Code Quality:** Ruff (100% compliant)

---

## 9. Verification Commands

```bash
# Run complete test suite (all tests run completely offline without an API key)
pytest

# Measure statement and branch coverage
pytest --cov=app --cov-report=term-missing

# Run code style and lint checks
ruff check .
ruff format --check .
```

---

## 10. Implementation Roadmap

- [x] **Phase 1: Project Setup & Sample Logs**
- [x] **Phase 2: Core Log Parsing & Failure Detection**
- [x] **Phase 3: Failure Fingerprinting & Grouping**
- [x] **Phase 4: Input Validation & Evidence Integrity**
- [x] **Phase 5: LLM Service & Report Generation**
  - Provider abstraction (`LLMProvider`, `MockLLMProvider`, `OpenAIProvider`).
  - Strict Pydantic response schemas (`AIAnalysis`, `LikelyCause`, `RecommendedAction`).
  - Bounded prompt construction with secret redaction.
  - Evidence reference verification.
  - Deterministic fallback analysis.
- [ ] **Phase 6: Streamlit Dashboard & REST API**

# LogLens AI — AI-Assisted Application Log Analyzer

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/tested_with-pytest-0a9edc.svg)](https://docs.pytest.org/)

**LogLens AI** is an intelligent log analysis engine designed to help software engineers rapidly inspect application and test logs, isolate errors and exceptions, extract multiline stack traces, group recurring failures via deterministic fingerprinting, and generate actionable, evidence-backed debugging summaries using LLMs.

> [!NOTE]
> **Development Status: Phase 6 Completed (FastAPI Backend)**
> Production-grade FastAPI REST API with endpoints for liveness (`GET /health`), offline readiness (`GET /health/ready`), and complete deterministic and AI-assisted log analysis (`POST /api/v1/analyze`). Features request correlation (`X-Request-ID`), execution timing headers (`X-Process-Time`), centralized error mapping, and interactive OpenAPI documentation (`/docs`, `/redoc`). Streamlit dashboard will be built in Phase 7.

---

## 1. Problem Statement

Modern software applications and automated test suites generate verbose, noisy logs. When incidents or test suite failures occur:
- Developers must manually sift through thousands of lines to spot relevant errors.
- Raw log inputs can be corrupted, oversized, or contain malicious line lengths designed to cause denial of service.
- Discrepancies between log splitters and parsers cause "off-by-one" line numbering errors.
- Generic LLM summaries often hallucinate nonexistent line numbers, invent ungrounded root causes, or expose credentials sent in raw prompts.

**LogLens AI** addresses these challenges through a strict 5-tier safety architecture:
1. **Pre-Parse Input Validation:** Rejects empty, invalidly encoded, or oversized payloads before parsing begins.
2. **Deterministic Processing Pipeline:** Parses lines, preserves exact 1-based source line numbers, extracts complete stack traces, and fingerprints failures deterministically into recurring failure groups.
3. **Evidence Integrity Verification:** Verifies every line reference, raw line text, group occurrence mapping, and aggregate metric against the original source log.
4. **Evidence-Anchored AI Triage:** Sends bounded, structured summaries to an LLM to generate root-cause hypotheses and investigation steps, strictly validating every returned line reference against original source logs with instant deterministic fallback upon any provider failure.
5. **FastAPI REST API Layer:** Provides typed, schema-validated endpoints with request correlation, non-leaking error responses, and offline readiness probes.

---

## 2. FastAPI Backend Architecture (Phase 6)

The REST API exposes the analysis pipeline via FastAPI, strictly separating transport and HTTP validation from core domain services:

```
[ HTTP Request: POST /api/v1/analyze ]
                    │
                    ▼
   [ Request Correlation Middleware ]
   - Generates or validates X-Request-ID header
   - Measures execution timing (X-Process-Time)
                    │
                    ▼
     [ Request Schema Validation ]
   - Pydantic model: AnalyzeLogRequest (extra="forbid")
   - Rejects non-JSON (400) or invalid types (422)
                    │
                    ▼
     [ Domain Input Validation ]
   - Validates size, line count, line length (413)
   - Checks UTF-8 encoding and empty payload (422)
                    │
                    ▼
   [ Deterministic Parsing & Grouping ]
   - Extracts ParsedLogEntry and FailureEvent list
   - Clusters into FailureGroup via SHA-256
   - Computes AnalysisMetrics
                    │
                    ▼
      [ Evidence Integrity Checks ]
   - Validates line bounds and content fidelity
                    │
                    ▼
       [ Optional AI Triage Layer ]
   - If include_ai=True and LLM_ENABLED: queries LLM
   - Strict evidence validation on AI references
   - Automatic fallback if LLM is disabled or fails
                    │
                    ▼
      [ Response Model Assembly ]
   - Assembles AnalyzeLogResponse (status: completed/warnings/fallback)
   - Emits response with X-Request-ID and X-Process-Time
```

### Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Liveness probe verifying process is up (`{"status": "ok", "service": "LogLens AI"}`). |
| `GET` | `/health/ready` | Readiness probe reporting pipeline and offline LLM availability. |
| `POST` | `/api/v1/analyze` | Executes complete deterministic analysis and optional AI triage. |
| `GET` | `/docs` | Interactive Swagger UI documentation. |
| `GET` | `/redoc` | Interactive ReDoc documentation. |
| `GET` | `/openapi.json` | OpenAPI 3.1 JSON specification. |

---

## 3. API Usage & Examples

### Starting the Local Server

Run the application using Uvicorn:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 1. Health Liveness Probe (`GET /health`)
```bash
curl -s http://127.0.0.1:8000/health
```
```json
{
  "status": "ok",
  "service": "LogLens AI"
}
```

### 2. Service Readiness Probe (`GET /health/ready`)
Evaluates operational readiness strictly offline without calling external APIs or requiring credentials:
```bash
curl -s http://127.0.0.1:8000/health/ready
```
```json
{
  "status": "ready",
  "llm_enabled": false,
  "llm_available": false
}
```

### 3. Log Analysis (`POST /api/v1/analyze`)

#### Deterministic Analysis (`include_ai: false`):
```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"log_text":"2026-10-14 10:30:00 ERROR app.service - Database connection failed","include_ai":false}'
```

#### Example Response:
```json
{
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "metrics": {
    "total_log_lines": 1,
    "total_error_entries": 1,
    "total_warning_entries": 0,
    "total_failure_events": 1,
    "unique_failure_groups": 1,
    "repeated_failure_groups": 0,
    "repeated_failure_events": 0,
    "most_frequent_failure_count": 1
  },
  "parsed_entries": [
    {
      "line_number": 1,
      "raw_line": "2026-10-14 10:30:00 ERROR app.service - Database connection failed",
      "timestamp": "2026-10-14 10:30:00",
      "level": "ERROR",
      "logger_name": "app.service",
      "message": "Database connection failed",
      "has_stack_trace": false
    }
  ],
  "failure_events": [
    {
      "event_id": "fe_00001",
      "event_type": "explicit_error",
      "primary_line_number": 1,
      "start_line_number": 1,
      "end_line_number": 1,
      "line_numbers": [1],
      "message": "Database connection failed",
      "level": "ERROR",
      "logger_name": "app.service"
    }
  ],
  "failure_groups": [
    {
      "fingerprint": "c4ca4238a0b923820dcc509a6f75849b3c4ca4238a0b923820dcc509a6f75849",
      "title": "explicit_error in app.service",
      "failure_category": "explicit_error",
      "representative_message": "Database connection failed",
      "occurrence_count": 1,
      "line_numbers": [1],
      "first_seen_line": 1,
      "last_seen_line": 1,
      "severity": "ERROR",
      "component": "app.service"
    }
  ],
  "parser_warnings": [],
  "ai_analysis": null,
  "analysis_source": "none",
  "processing_time_ms": 1.45
}
```

---

## 4. Standardized Error Handling

All error responses return a standardized `ErrorResponse` envelope without exposing internal paths, stack traces, or credentials:

```json
{
  "error": {
    "code": "LOG_TOO_LARGE",
    "message": "Log payload size (2097152 bytes) exceeds limit (1048576 bytes)",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "limit": 1048576,
    "actual": 2097152
  }
}
```

### Status Code Mapping

| Status Code | Error Code | Trigger Condition |
| :--- | :--- | :--- |
| `400 Bad Request` | `MALFORMED_JSON` | Body is not valid JSON. |
| `413 Content Too Large` | `LOG_TOO_LARGE` | Byte length exceeds `MAX_LOG_SIZE_BYTES`. |
| `413 Content Too Large` | `TOO_MANY_LOG_LINES` | Line count exceeds `MAX_LOG_LINES`. |
| `413 Content Too Large` | `LOG_LINE_TOO_LONG` | Single line exceeds `MAX_LOG_LINE_LENGTH`. |
| `422 Unprocessable Content`| `EMPTY_LOG_INPUT` | Input is empty or whitespace-only. |
| `422 Unprocessable Content`| `VALIDATION_ERROR` | Schema mismatch, missing fields, or unknown extra fields. |
| `500 Internal Server Error`| `INTERNAL_SERVER_ERROR` | Unexpected internal exception (sanitized response). |
| `500 Internal Server Error`| `EVIDENCE_INTEGRITY_VIOLATION` | Internal evidence consistency check failed. |

---

## 5. Environment Configuration

Configured via environment variables or a local `.env` file (`app/core/config.py`):

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `APP_NAME` | `str` | `"LogLens AI"` | Application name. |
| `APP_ENV` | `str` | `"development"` | Deployment environment. |
| `DEBUG` | `bool` | `False` | Debug mode. |
| `MAX_LOG_SIZE_BYTES` | `int` | `1048576` (1 MiB) | Maximum accepted raw log payload in bytes. |
| `MAX_LOG_LINES` | `int` | `20000` | Maximum accepted line count for log input. |
| `MAX_LOG_LINE_LENGTH` | `int` | `16384` | Maximum accepted characters per individual line. |
| `LLM_ENABLED` | `bool` | `False` | Master switch for LLM requests. |
| `LLM_PROVIDER` | `str \| None` | `None` | Provider identifier: `'mock'` or `'openai'`. |
| `LLM_API_KEY` | `str \| None` | `None` | Secret API key (never required for tests). |
| `LLM_MODEL` | `str \| None` | `None` | Model identifier (e.g., `'gpt-4o-mini'`). |
| `LLM_TIMEOUT_SECONDS` | `float` | `30.0` | Timeout in seconds for LLM calls. |

---

## 6. Testing & Quality Verification

All 275 tests run completely offline without internet access or real LLM credentials:

```bash
# Run complete test suite (Phases 1 through 6)
pytest

# Run tests with statement and branch coverage report
pytest --cov=app --cov-report=term-missing

# Run code style and formatting checks
ruff check .
ruff format --check .
```

---

## 7. Implementation Roadmap

- [x] **Phase 1: Project Setup & Sample Logs**
- [x] **Phase 2: Core Log Parsing & Failure Detection**
- [x] **Phase 3: Failure Fingerprinting & Grouping**
- [x] **Phase 4: Input Validation & Evidence Integrity**
- [x] **Phase 5: LLM Service & Report Generation**
- [x] **Phase 6: FastAPI Backend**
  - Application factory with CORS, request correlation, and timing middleware.
  - Health (`/health`) and readiness (`/health/ready`) probe endpoints.
  - Log analysis endpoint (`/api/v1/analyze`) with deterministic and AI fallback.
  - Strict Pydantic request and response schemas with standardized error formatting.
  - Interactive OpenAPI documentation (`/docs`, `/redoc`, `/openapi.json`).
  - Automated offline ASGI test suite (30 API tests, 275 total tests, 91% code coverage).
- [ ] **Phase 7: Streamlit Dashboard**

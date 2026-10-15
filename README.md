# LogLens AI — AI-Assisted Application Log Analyzer

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/tested_with-pytest-0a9edc.svg)](https://docs.pytest.org/)

**LogLens AI** is an intelligent log analysis engine designed to help software engineers rapidly inspect application and test logs, isolate errors and exceptions, extract multiline stack traces, group recurring failures via deterministic fingerprinting, and generate actionable, evidence-backed debugging summaries using LLMs.

> [!NOTE]
> **Development Status: Phase 7 Completed (Streamlit Dashboard)**
> Polished, responsive Streamlit web console allowing developers to paste logs, upload `.log`/`.txt` files, or select fixture samples. Displays summary metrics, clustered failure groups with occurrence navigation, stack traces, interactive 1-based source viewer with evidence highlighting, and AI triage summaries with deterministic fallback indicators. Communicates with the FastAPI backend over HTTP (`LOGLENS_API_URL`).

---

## 1. Problem Statement

Modern software applications and automated test suites generate verbose, noisy logs. When incidents or test suite failures occur:
- Developers must manually sift through thousands of lines to spot relevant errors.
- Raw log inputs can be corrupted, oversized, or contain malicious line lengths designed to cause denial of service.
- Discrepancies between log splitters and parsers cause "off-by-one" line numbering errors.
- Generic LLM summaries often hallucinate nonexistent line numbers, invent ungrounded root causes, or expose credentials sent in raw prompts.

**LogLens AI** addresses these challenges through a strict 6-tier safety architecture:
1. **Pre-Parse Input Validation:** Rejects empty, invalidly encoded, or oversized payloads before parsing begins.
2. **Deterministic Processing Pipeline:** Parses lines, preserves exact 1-based source line numbers, extracts complete stack traces, and fingerprints failures deterministically into recurring failure groups.
3. **Evidence Integrity Verification:** Verifies every line reference, raw line text, group occurrence mapping, and aggregate metric against the original source log.
4. **Evidence-Anchored AI Triage:** Sends bounded, structured summaries to an LLM to generate root-cause hypotheses and investigation steps, strictly validating every returned line reference against original source logs with instant deterministic fallback upon any provider failure.
5. **FastAPI REST API Layer:** Provides typed, schema-validated endpoints with request correlation, non-leaking error responses, and offline readiness probes.
6. **Streamlit Developer Console:** Delivers an intuitive, interactive frontend with real-time health checks, file upload guards, grouped failure exploration, and original source highlighting.

---

## 2. Streamlit Dashboard (Phase 7)

The frontend is built using Streamlit and interacts exclusively with the FastAPI REST API, maintaining strict decoupling between UI rendering and backend processing.

```
[ Developer Browser ]
         │
         ▼
[ Streamlit Web Console (frontend/streamlit_app.py) ]
  ├── Ingestion Sidebar: Paste, Upload (.log, .txt), or Sample Log Loading
  ├── Header & Probes: Liveness & Offline LLM Capability Badges
  ├── Metric Cards: Total Lines, Failure Events, Unique & Repeated Groups
  ├── Grouped Explorer: Recurrence sorting, occurrence navigation, stack traces
  ├── Source Viewer: 1-based line numbering with color-coded evidence highlights
  └── AI Insights Panel: Root-cause hypotheses, priority actions, fallback alerts
         │
         ▼ HTTP (requests)
[ FastAPI Backend (app/main.py) ]
  ├── GET /health & GET /health/ready
  └── POST /api/v1/analyze
```

### Dashboard Features

- **Dual Ingestion Modes:** Paste raw logs directly from CI or upload `.log` and `.txt` files with strict client-side UTF-8 validation and size indicators.
- **Sample Log Fixtures:** Instant one-click loading of bundled test fixtures (`recurring_failures.log`, `sample_application.log`, `sample_test_failure.log`).
- **Real-Time Backend Status:** Visual status indicator reporting backend connection state and offline LLM availability.
- **Failure Group Explorer:** Interactive selection of clustered failure patterns with sorting (Most Frequent, Earliest, Severity) and occurrence switching.
- **Syntax-Preserved Stack Traces:** Code blocks preserving indentation, error messages, and line numbers.
- **Original Source Viewer:** Renders original submitted logs with 1-based numbering, context windowing (±10 lines or full log), and distinct color-coded highlights:
  - 🔴 **Primary Failure Line:** First-seen error declaration or exception line.
  - 🟡 **Context / Trace:** Supporting stack-trace or multiline occurrence span.
  - 🔵 **AI Cited Evidence:** Line verified as supporting evidence for AI root causes.
- **AI Triage & Fallback Reporting:** Clearly distinguishes true LLM-generated reports from deterministic fallback insights. Clickable citation buttons automatically center and highlight corresponding source lines.
- **Parser Warnings:** Dedicated tab displaying non-fatal parsing limitations without exposing internal stack traces.

---

## 3. Local Startup Guide

> [!TIP]
> Ensure the virtual environment is activated (`source .venv/bin/activate`) or use the provided startup scripts below, as `uvicorn` and `streamlit` are installed inside `.venv`.

### Option A: Single-Command Launch (Recommended)
Starts the backend, waits for it to become healthy, and opens the dashboard:
```bash
./run_app.sh
```

### Option B: Two-Terminal Startup

**Terminal 1: Start Backend**
```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# Or directly: ./run_backend.sh
```

**Terminal 2: Start Dashboard**
```bash
source .venv/bin/activate
streamlit run frontend/streamlit_app.py
# Or directly: ./run_dashboard.sh
```

The dashboard will open in your browser at `http://localhost:8501`.

### Configuration Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LOGLENS_API_URL` | `http://127.0.0.1:8000` | Base URL of the running FastAPI backend. |
| `MAX_LOG_SIZE_BYTES` | `1048576` (1 MiB) | Maximum accepted raw log payload in bytes. |
| `MAX_LOG_LINES` | `20000` | Maximum accepted line count for log input. |
| `MAX_LOG_LINE_LENGTH` | `16384` | Maximum accepted characters per individual line. |
| `LLM_ENABLED` | `False` | Master switch for LLM requests (deterministic fallback when `False`). |
| `LLM_PROVIDER` | `None` | Provider identifier: `'mock'` or `'openai'`. |
| `LLM_API_KEY` | `None` | Secret API key (never required for offline operation or tests). |

---

## 4. REST API Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Liveness probe verifying process is up (`{"status": "ok", "service": "LogLens AI"}`). |
| `GET` | `/health/ready` | Readiness probe reporting pipeline and offline LLM availability. |
| `POST` | `/api/v1/analyze` | Executes complete deterministic analysis and optional AI triage. |
| `GET` | `/docs` | Interactive Swagger UI documentation. |
| `GET` | `/redoc` | Interactive ReDoc documentation. |
| `GET` | `/openapi.json` | OpenAPI 3.1 JSON specification. |

### Quick `curl` Example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"log_text":"2026-10-14 10:30:00 ERROR app.service - Database connection failed","include_ai":false}'
```

---

## 5. Testing & Quality Verification

All 307 tests run completely offline without internet access or real LLM credentials:

```bash
# Run complete test suite (Phases 1 through 7)
pytest

# Run tests with statement and branch coverage report
pytest --cov=app --cov=frontend --cov-report=term-missing

# Run frontend tests specifically
pytest tests/test_frontend_api_client.py tests/test_frontend_utils.py tests/test_frontend_components.py -v

# Run code style and formatting checks
ruff check .
ruff format --check .
```

---

## 6. Implementation Roadmap

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
- [x] **Phase 7: Streamlit Dashboard**
  - Dual ingestion: multiline paste and `.log`/`.txt` file upload with UTF-8 decoding guards.
  - Bundled sample fixture loading (`recurring_failures.log`, `sample_application.log`, `sample_test_failure.log`).
  - Summary metric cards, failure group explorer with sorting and occurrence navigation.
  - Syntax-preserving stack trace code blocks.
  - Original source log viewer with context windowing and color-coded evidence highlights.
  - AI triage panel with actionable citation navigation and deterministic fallback alerts.
  - Automated frontend unit test suite (32 tests covering API client, utils, and UI components).

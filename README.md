# LogLens AI — AI-Assisted Application Log Analyzer

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/tested_with-pytest-0a9edc.svg)](https://docs.pytest.org/)

**LogLens AI** is an intelligent log analysis engine designed to help software engineers rapidly inspect application and test logs, isolate errors and exceptions, extract multiline stack traces, group recurring failures via deterministic fingerprinting, and generate actionable, evidence-backed debugging summaries using LLMs.

> [!NOTE]
> **Development Status: Phase 1 Completed (Project Setup & Sample Logs)**
> The project scaffolding, environment configuration, testing framework, and sample log fixtures are fully established. Core log parsing, failure detection, fingerprinting, grouping, LLM integration, REST API, and Streamlit dashboard will be implemented in subsequent phases.

---

## 1. Problem Statement

Modern software applications and automated test suites generate verbose, noisy logs. When incidents or test suite failures occur:
- Developers must manually sift through thousands of lines to spot relevant errors.
- The same underlying root cause often appears dozens or hundreds of times with slight parameter variations (such as distinct request IDs or timestamps), cluttering investigation.
- Multiline exception stack traces are difficult to parse deterministically without losing context.
- While LLMs can provide insightful triage summaries, raw logs are often too large to send directly, may contain sensitive data, and LLM responses risk "hallucinating" line references or root causes if not bound to verifiable evidence.

**LogLens AI** addresses these challenges through a hybrid architecture:
1. **Deterministic Processing Pipeline:** Parses lines, preserves exact 1-based source line numbers, extracts complete stack traces, and fingerprints failures deterministically into recurring failure groups.
2. **Evidence-Anchored AI Triage:** Sends bounded, structured summaries to an LLM to generate root-cause hypotheses and investigation steps, strictly validating every returned line reference against original source logs.
3. **Graceful Fallback:** If LLM access is disabled or unavailable, the deterministic analysis remains fully functional and informative.

---

## 2. Planned Capabilities

- **Multi-Format Ingestion:** Accept raw text, file uploads, and API payloads for Python tracebacks, standard loggers, and test runners.
- **Robust Validation:** Enforce size limits (default 1 MiB / 20,000 lines), UTF-8 verification, and input sanitation.
- **Deterministic Fingerprinting:** Group recurring failures by normalizing volatile variables (UUIDs, request IDs, memory addresses) while preserving structural exception signatures.
- **Verifiable Evidence References:** Anchor every error, failure group, and AI finding to exact 1-based source line numbers (e.g., `L14-L22`).
- **Provider-Agnostic LLM Layer:** Support pluggable LLM backends (OpenAI, Anthropic, or mock) with strict JSON schema validation.
- **Developer Interfaces:** Expose a FastAPI REST API and a lightweight Streamlit dashboard with side-by-side log exploration.

---

## 3. Technology Stack

### Backend & Core
- **Language:** Python 3.11+ (Tested on Python 3.12)
- **API Framework (Planned):** FastAPI & Uvicorn
- **Data Validation:** Pydantic v2 & Pydantic-Settings
- **Environment Management:** python-dotenv

### Log Processing (Upcoming)
- Python Standard Library (`re`, `datetime`, `hashlib`, `typing`)
- Deterministic regex-based tokenization and stack trace extraction

### Frontend (Upcoming)
- Streamlit for interactive incident triage and visualization

### Quality & Testing
- **Test Framework:** pytest & pytest-cov
- **Linter & Formatter:** Ruff (fast, PEP 8 compliant)

---

## 4. Repository Structure

```
LogCheck/
├── app/
│   ├── __init__.py           # Package version and metadata
│   ├── main.py               # Application entry point
│   ├── api/                  # FastAPI routers and endpoints (Phase 4)
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py         # Typed settings with validation
│   ├── models/               # Domain and schema models (Phase 2+)
│   ├── services/             # Parser, grouping, and LLM services (Phase 2-4)
│   └── utils/                # Line reference and helper utilities
├── frontend/
│   └── .gitkeep              # Streamlit dashboard (Phase 5)
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared test fixtures and isolated settings
│   ├── test_project_setup.py # Scaffolding and configuration verification
│   └── fixtures/             # Realistic test log samples
│       ├── sample_application.log
│       ├── sample_test_failure.log
│       ├── recurring_failures.log
│       └── malformed.log
├── examples/                 # Exploratory sample logs for documentation
│   ├── application_error.log
│   ├── recurring_failures.log
│   └── test_failures.log
├── docs/                     # Architectural and API documentation
├── .docs/                    # Project specifications and walkthroughs
├── .env.example              # Environment configuration template
├── .gitignore                # Git ignore rules
├── .python-version           # Target Python version (3.12)
├── pyproject.toml            # Canonical project configuration
├── requirements.txt          # Pinned dependency definitions
└── README.md                 # Project documentation
```

---

## 5. Prerequisites

- **Linux / Ubuntu** (or compatible Unix-like OS, macOS, WSL2)
- **Python 3.11 or Python 3.12**
- **Git**

---

## 6. Installation & Quickstart

### 1. Clone Repository & Create Virtual Environment

```bash
# Clone the repository
git clone <repo-url>
cd LogCheck

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
# Upgrade pip and install all project dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file from the provided template:

```bash
cp .env.example .env
```

The application defaults to safe local development settings without requiring an LLM API key:

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `"LogLens AI"` | Application identifier |
| `APP_ENV` | `"development"` | Environment name |
| `DEBUG` | `false` | Enable verbose debug output |
| `MAX_LOG_SIZE_BYTES` | `1048576` | Maximum log size in bytes (1 MiB) |
| `MAX_LOG_LINES` | `20000` | Maximum line count accepted |
| `LLM_ENABLED` | `false` | Enable/disable LLM assistance |
| `LLM_PROVIDER` | `None` | Provider (`mock`, `openai`, etc.) |
| `LLM_API_KEY` | `None` | Optional API key |
| `LLM_MODEL` | `None` | Target LLM model name |
| `LLM_TIMEOUT_SECONDS`| `30.0` | Timeout for external LLM calls |

---

## 7. Testing & Code Quality

### Running Automated Tests

Run the test suite with verbose output and coverage reporting:

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=term-missing
```

### Code Formatting & Linting

We use [Ruff](https://github.com/astral-sh/ruff) for fast, consistent styling:

```bash
# Check code for lint violations
ruff check .

# Check code formatting without modifying files
ruff format --check .

# Automatically apply formatting
ruff format .
```

---

## 8. Sample Log Fixtures

The repository includes four realistic log fixtures under `tests/fixtures/` and sample logs in `examples/`:

1. **`sample_application.log`**: Standard microservice logs featuring INFO lifecycle events, a Redis timeout WARNING, and an unhandled `ConnectionTimeoutError` with multiline Python traceback followed by graceful recovery messages.
2. **`sample_test_failure.log`**: A pytest runner output stream exhibiting 4 passing unit tests and 1 failing test with an explicit `AssertionError` and test summary.
3. **`recurring_failures.log`**: High-frequency failure scenario exhibiting 3 occurrences of `DatabaseConnectionError` with variable request IDs (`req-a1b2c3d4`, `req-e5f6g7h8`, `req-11223344`) alongside a distinct `ValidationError`.
4. **`malformed.log`**: Edge-case testing fixture containing corrupted timestamp headers, unstructured output from legacy subshells, empty lines, and benign text containing the keyword "error".

---

## 9. Security & Privacy Notice

> [!WARNING]
> Real-world application logs frequently contain sensitive data, including API keys, passwords, database connection strings, bearer tokens, and personally identifiable information (PII).
> 
> - **Never** upload logs containing production secrets without scrubbing.
> - LogLens AI provides an `LLM_ENABLED=false` configuration switch to perform 100% offline, deterministic log analysis without sending any data to third-party AI providers.
> - When LLM assistance is enabled in future phases, only bounded, pre-filtered error evidence will be submitted to the configured provider.

---

## 10. Implementation Roadmap

- [x] **Phase 1: Project Setup & Sample Logs** *(Completed)*
  - Initial repository layout, dependencies, and virtual environment.
  - Typed configuration management using Pydantic Settings.
  - Realistic test log fixtures and initial verification test suite.
  - Ruff linting and formatting configuration.
- [ ] **Phase 2: Core Log Parsing & Failure Detection**
  - Line-by-line parsing with 1-based source line mapping.
  - Detection of error levels, exceptions, and multiline stack traces.
- [ ] **Phase 3: Failure Fingerprinting & Grouping**
  - Variable normalization (UUIDs, request IDs, hex addresses).
  - Deterministic SHA-256 fingerprinting and occurrence grouping.
- [ ] **Phase 4: LLM Service & REST API**
  - Provider-agnostic LLM interface with strict evidence validation.
  - FastAPI endpoints (`/health`, `/api/v1/analyze`).
- [ ] **Phase 5: Streamlit Dashboard & Documentation**
  - Interactive web UI with side-by-side evidence inspection.
  - End-to-end user guide and internship portfolio documentation.

# LogLens AI — AI-Assisted Application Log Analyzer

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/tested_with-pytest-0a9edc.svg)](https://docs.pytest.org/)

**LogLens AI** is an intelligent log analysis engine designed to help software engineers rapidly inspect application and test logs, isolate errors and exceptions, extract multiline stack traces, group recurring failures via deterministic fingerprinting, and generate actionable, evidence-backed debugging summaries using LLMs.

> [!NOTE]
> **Development Status: Phase 2 Completed (Log Parsing & Stack Trace Extraction)**
> Deterministic line-by-line parsing, level normalization, Python/Java traceback extraction, assertion failure identification, and 1-based source line mapping are fully implemented. Failure fingerprinting, recurring-failure grouping, LLM integration, REST API, and Streamlit dashboard will be implemented in subsequent phases.

---

## 1. Problem Statement

Modern software applications and automated test suites generate verbose, noisy logs. When incidents or test suite failures occur:
- Developers must manually sift through thousands of lines to spot relevant errors.
- The same underlying root cause often appears dozens or hundreds of times with slight parameter variations, cluttering investigation.
- Multiline exception stack traces are difficult to parse deterministically without losing context or absorbing subsequent valid logs.
- While LLMs can provide insightful triage summaries, raw logs are often too large to send directly, and LLM responses risk "hallucinating" line references or root causes if not bound to verifiable evidence.

**LogLens AI** addresses these challenges through a hybrid architecture:
1. **Deterministic Processing Pipeline:** Parses lines, preserves exact 1-based source line numbers, extracts complete stack traces, and fingerprints failures deterministically into recurring failure groups.
2. **Evidence-Anchored AI Triage:** Sends bounded, structured summaries to an LLM to generate root-cause hypotheses and investigation steps, strictly validating every returned line reference against original source logs.
3. **Graceful Fallback:** If LLM access is disabled or unavailable, the deterministic analysis remains fully functional and informative.

---

## 2. Phase 2 Capabilities & Parser Architecture

Phase 2 introduces a completely offline, deterministic log parsing engine (`app/services/log_parser.py`):

```
Raw Multiline Log Text
         │
         ▼
[ Step 1: Line Ingestion & Indexing ] ──> Preserves exact 1-based line numbers & raw content
         │
         ▼
[ Step 2: Metadata & Level Parsing ] ──> Timestamp, logger, level extraction (bracket, spaced, JSON)
         │
         ▼
[ Step 3: Exception & Trace Extraction ]
   ├── Python Tracebacks: Headers, frames, code context, chaining markers, terminal exceptions
   ├── Java Stack Traces: Exception declarations, `at` frames, `Caused by:`, suppressed exceptions
   └── Test Runner Output: Pytest & Unittest failure sections, assertion messages
         │
         ▼
[ Step 4: Event Assembly & Line Linking ] ──> Groups lines into logical `FailureEvent`s; links `ParsedLogEntry`
         │
         ▼
[ Step 5: Summary Metrics Calculation ] ──> total_lines, error_count, failure_event_count, etc.
```

### Supported Log Formats
- **Standard Bracketed Logs:** `2026-10-14 08:30:01,102 [INFO] app.server: Starting worker`
- **Spaced Logger Format:** `2026-10-14 10:15:30 INFO application.worker - Job started`
- **Bracket-Prefixed Severity:** `[ERROR] PaymentService - Transaction failed`
- **Colon-Prefixed Severity:** `ERROR: Unable to connect to host`
- **JSON Structured Lines:** `{"timestamp": "...", "level": "ERROR", "logger": "...", "message": "..."}`
- **Corrupted / Custom Streams:** `[2026/10/14-09:40:00] !!! UNUSUAL_ALERT !!! ...`
- **Unstructured / Malformed Lines:** Emitted by subshells or plain text; preserved without crashing.

### Key Distinctions
- **Log Entry vs. Failure Event:** A log entry (`ParsedLogEntry`) represents a single physical line of text with its line number and parsed metadata. A failure event (`FailureEvent`) represents a logical failure or exception that may span multiple lines (an explicit error line, traceback header, 10 stack frames, code context lines, and terminal exception declaration).
- **False-Positive Resistance:** Ordinary informational messages containing the word "error" or "warning" (e.g. `INFO app - The previous error has been resolved`) retain their `INFO` severity and never generate false failure events.
- **Traceback Boundaries:** Parsers strictly terminate traceback consumption when a subsequent structured log entry or unindented text is encountered. Subsequent log lines are never absorbed into preceding tracebacks.

---

## 3. Real Parser Output Example

Given the raw log snippet:

```log
2026-10-14 08:30:05,432 [ERROR] app.database: Failed to acquire connection
Traceback (most recent call last):
  File "/srv/app/services/payment.py", line 142, in process_transaction
    async with db.transaction() as conn:
app.database.exceptions.ConnectionTimeoutError: Timed out waiting for connection
2026-10-14 08:30:06,001 [INFO] app.server: Health check passed
```

Executing `parse_log_text(log)` produces:

```json
{
  "total_lines": 6,
  "entries": [
    {
      "line_number": 1,
      "raw_line": "2026-10-14 08:30:05,432 [ERROR] app.database: Failed to acquire connection",
      "timestamp": "2026-10-14 08:30:05,432",
      "level": "ERROR",
      "logger_name": "app.database",
      "message": "Failed to acquire connection",
      "category": "error",
      "failure_event_id": "event-1"
    },
    {
      "line_number": 2,
      "raw_line": "Traceback (most recent call last):",
      "timestamp": null,
      "level": null,
      "logger_name": null,
      "message": "Traceback (most recent call last):",
      "category": "traceback_header",
      "failure_event_id": "event-1"
    },
    {
      "line_number": 3,
      "raw_line": "  File \"/srv/app/services/payment.py\", line 142, in process_transaction",
      "timestamp": null,
      "level": null,
      "logger_name": null,
      "message": "File \"/srv/app/services/payment.py\", line 142, in process_transaction",
      "category": "stack_frame",
      "failure_event_id": "event-1"
    },
    {
      "line_number": 4,
      "raw_line": "    async with db.transaction() as conn:",
      "timestamp": null,
      "level": null,
      "logger_name": null,
      "message": "    async with db.transaction() as conn:",
      "category": "stack_frame",
      "failure_event_id": "event-1"
    },
    {
      "line_number": 5,
      "raw_line": "app.database.exceptions.ConnectionTimeoutError: Timed out waiting for connection",
      "timestamp": null,
      "level": null,
      "logger_name": null,
      "message": "app.database.exceptions.ConnectionTimeoutError: Timed out waiting for connection",
      "category": "exception",
      "failure_event_id": "event-1"
    },
    {
      "line_number": 6,
      "raw_line": "2026-10-14 08:30:06,001 [INFO] app.server: Health check passed",
      "timestamp": "2026-10-14 08:30:06,001",
      "level": "INFO",
      "logger_name": "app.server",
      "message": "Health check passed",
      "category": "normal",
      "failure_event_id": null
    }
  ],
  "failure_events": [
    {
      "event_id": "event-1",
      "event_type": "exception",
      "exception_type": "ConnectionTimeoutError",
      "message": "Timed out waiting for connection",
      "primary_line_number": 5,
      "start_line_number": 1,
      "end_line_number": 5,
      "line_numbers": [1, 2, 3, 4, 5],
      "stack_trace": [
        "Traceback (most recent call last):",
        "  File \"/srv/app/services/payment.py\", line 142, in process_transaction",
        "    async with db.transaction() as conn:",
        "app.database.exceptions.ConnectionTimeoutError: Timed out waiting for connection"
      ],
      "timestamp": "2026-10-14 08:30:05,432",
      "level": "ERROR",
      "logger_name": "app.database"
    }
  ],
  "error_count": 1,
  "warning_count": 0,
  "failure_event_count": 1,
  "stack_trace_line_count": 4,
  "parser_warnings": []
}
```

---

## 4. Current Limitations

- **Binary Logs:** Only plain-text and UTF-8 encoded log files are currently supported.
- **Java Source Lookup:** Java exception stack traces extract class names, method names, and file numbers, but do not perform classpath or source-code decompilation.
- **Fingerprinting & Recurrence Counts:** Not yet implemented; planned for Phase 3.
- **LLM Summaries & REST API:** Not yet implemented; planned for Phase 4.

---

## 5. Technology Stack

### Backend & Core
- **Language:** Python 3.11+ (Tested on Python 3.12)
- **Data Validation:** Pydantic v2 & Pydantic-Settings
- **Environment Management:** python-dotenv

### Log Processing (Phase 2)
- Python Standard Library (`re`, `json`, `enum`)
- Deterministic regex tokenization and traceback extraction

### Quality & Testing
- **Test Framework:** pytest & pytest-cov (86 passing tests, 89% coverage)
- **Linter & Formatter:** Ruff

---

## 6. Installation & Quickstart

```bash
# Clone repository and enter directory
git clone <repo-url>
cd LogCheck

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run all automated tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=term-missing

# Run linting checks
ruff check .
ruff format --check .
```

---

## 7. Implementation Roadmap

- [x] **Phase 1: Project Setup & Sample Logs**
  - Initial repository layout, dependencies, and virtual environment.
  - Typed configuration management using Pydantic Settings.
  - Realistic test log fixtures and initial verification test suite.
- [x] **Phase 2: Core Log Parsing & Failure Detection**
  - Line-by-line parsing with 1-based source line mapping.
  - Normalization of log severity levels (WARN->WARNING, FATAL->CRITICAL).
  - Multi-line Python traceback parsing and exception-chaining preservation.
  - Java stack trace and `Caused by:` chain extraction.
  - Pytest assertion failures and test failure section extraction.
  - Distinct separation of log entries vs logical failure events.
- [ ] **Phase 3: Failure Fingerprinting & Grouping**
  - Variable normalization (UUIDs, request IDs, hex addresses).
  - Deterministic SHA-256 fingerprinting and occurrence grouping.
- [ ] **Phase 4: LLM Service & REST API**
  - Provider-agnostic LLM interface with strict evidence validation.
  - FastAPI endpoints (`/health`, `/api/v1/analyze`).
- [ ] **Phase 5: Streamlit Dashboard & Documentation**
  - Interactive web UI with side-by-side evidence inspection.
  - End-to-end user guide and portfolio documentation.

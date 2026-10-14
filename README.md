# LogLens AI — AI-Assisted Application Log Analyzer

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/tested_with-pytest-0a9edc.svg)](https://docs.pytest.org/)

**LogLens AI** is an intelligent log analysis engine designed to help software engineers rapidly inspect application and test logs, isolate errors and exceptions, extract multiline stack traces, group recurring failures via deterministic fingerprinting, and generate actionable, evidence-backed debugging summaries using LLMs.

> [!NOTE]
> **Development Status: Phase 3 Completed (Failure Fingerprinting & Grouping)**
> Deterministic failure fingerprinting (SHA-256), conservative variable normalization (UUIDs, request IDs, memory addresses), recurring failure aggregation, and aggregate failure metrics are fully implemented and verified. LLM integration, REST API, and Streamlit dashboard will be implemented in subsequent phases.

---

## 1. Problem Statement

Modern software applications and automated test suites generate verbose, noisy logs. When incidents or test suite failures occur:
- Developers must manually sift through thousands of lines to spot relevant errors.
- The same underlying root cause often appears dozens or hundreds of times with slight parameter variations (such as changing request IDs, UUIDs, or timestamps), cluttering investigation.
- Multiline exception stack traces are difficult to parse deterministically without losing context or absorbing subsequent valid logs.
- While LLMs can provide insightful triage summaries, raw logs are often too large to send directly, and LLM responses risk "hallucinating" line references or root causes if not bound to verifiable evidence.

**LogLens AI** addresses these challenges through a hybrid architecture:
1. **Deterministic Processing Pipeline:** Parses lines, preserves exact 1-based source line numbers, extracts complete stack traces, and fingerprints failures deterministically into recurring failure groups.
2. **Evidence-Anchored AI Triage:** Sends bounded, structured summaries to an LLM to generate root-cause hypotheses and investigation steps, strictly validating every returned line reference against original source logs.
3. **Graceful Fallback:** If LLM access is disabled or unavailable, the deterministic analysis remains fully functional and informative.

---

## 2. Phase 3 Capabilities & Pipeline Architecture

Phase 3 introduces a completely offline, deterministic failure fingerprinting and grouping engine:

```
Parsed FailureEvents (from Phase 2)
              │
              ▼
[ Step 1: Signature Extraction ] ──────────> Extract (failure_type, exception_type, message, component)
              │
              ▼
[ Step 2: Conservative Normalization ] ────> Volatile variables replaced (<UUID>, <MEMORY_ADDRESS>, <REQUEST_ID>)
              │                              Semantic data preserved (timeouts, status codes, error codes)
              ▼
[ Step 3: Canonical Serialization ] ───────> Deterministic string: category=...|component=...|exception=...|message=...
              │
              ▼
[ Step 4: SHA-256 Fingerprint ] ───────────> 64-character hex hash (independent of Python hash seed)
              │
              ▼
[ Step 5: Failure Grouping & Aggregation ] > Aggregate occurrences, union line numbers, first/last seen
              │
              ▼
[ Step 6: Deterministic Ordering ] ────────> 1. occurrence_count DESC, 2. first_seen_line ASC, 3. fingerprint ASC
              │
              ▼
[ Step 7: Analysis Metrics Calculation ] ──> unique_groups, repeated_groups, repeated_events, max_count
```

### Normalization Rules

Volatile parameters that vary across identical failure causes are normalized safely:
- **UUIDs:** `550e8400-e29b-41d4-a716-446655440000` $\rightarrow$ `<UUID>`
- **Memory Addresses:** `0x7f12ab34` $\rightarrow$ `<MEMORY_ADDRESS>`
- **Request Identifiers:** `req-a1b2c3d4` or `request 12345` $\rightarrow$ `<REQUEST_ID>`
- **Entity Tokens:** `tx-99128` $\rightarrow$ `<TX_ID>`, `job-981` $\rightarrow$ `<JOB_ID>`, `order_id=ord_123` $\rightarrow$ `order_id=<ORDER_ID>`
- **Entity Phrases:** `Payment 10234` $\rightarrow$ `Payment <ENTITY_ID>`, `users/42` $\rightarrow$ `users/<ENTITY_ID>`

**What is Intentionally Preserved:**
- Timeouts and durations (`after 5.0s` vs `after 60.0s` remain distinct).
- HTTP status codes (`503 Service Unavailable` vs `404 Not Found` remain distinct).
- Database error codes (`ORA-00001`, `SQLSTATE 23505`).
- Port numbers, version strings, and assertion expressions.

### Failure Event vs. Failure Group

- **Failure Event (`FailureEvent`):** Represents an individual occurrence of a failure within the log stream (with its own event ID, primary line number, stack trace, and timestamp).
- **Failure Group (`FailureGroup`):** Represents a logical collection of recurring failure events sharing the same deterministic SHA-256 fingerprint.

### Analysis Metrics Definitions

- `total_log_lines`: Total physical lines in the log.
- `total_error_entries`: Entries classified explicitly as ERROR or CRITICAL.
- `total_warning_entries`: Entries classified explicitly as WARNING.
- `total_failure_events`: Total individual failure events identified.
- `unique_failure_groups`: Number of distinct fingerprints.
- `repeated_failure_groups`: Groups with `occurrence_count > 1`.
- `repeated_failure_events`: Occurrences belonging to repeated groups (`sum(count for g in groups if count > 1)`).
- `most_frequent_failure_count`: Largest single group occurrence count.

---

## 3. Real Example of End-to-End Analysis

Processing `tests/fixtures/recurring_failures.log` through `analyze_failures()`:

```python
from pathlib import Path
from app.services.log_parser import parse_log_text
from app.services.grouping import analyze_failures

log_text = Path("tests/fixtures/recurring_failures.log").read_text()
parsing_result = parse_log_text(log_text)
analysis = analyze_failures(parsing_result)
```

### Metrics Output:
```json
{
  "total_log_lines": 34,
  "total_error_entries": 4,
  "total_warning_entries": 0,
  "total_failure_events": 4,
  "unique_failure_groups": 2,
  "repeated_failure_groups": 1,
  "repeated_failure_events": 3,
  "most_frequent_failure_count": 3
}
```

### Grouped Failures:
1. **Group 1 (Repeated Failure):**
   - **Title:** `DatabaseConnectionError: Connection lost to database cluster primary`
   - **Fingerprint:** `72907e419faff67e93066426a148dc4cfb8dd9cea92d3338c33f06c83b2ef1a8`
   - **Occurrence Count:** `3`
   - **Source Lines:** `[2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 26, 27, 28, 29, 30, 31, 32]`
   - **First Seen:** Line 8, **Last Seen:** Line 32
2. **Group 2 (Isolated Failure):**
   - **Title:** `ValidationError: Missing required field 'shipping_address'`
   - **Fingerprint:** `b9e399ea2dcb785f473b21b4f240d63682b74c098fbaa13693f22e2985faaa4d`
   - **Occurrence Count:** `1`
   - **Source Lines:** `[18, 19, 20, 21, 22, 23, 24]`
   - **First Seen:** Line 24, **Last Seen:** Line 24

---

## 4. Technology Stack

### Backend & Core
- **Language:** Python 3.11+ (Tested on Python 3.12)
- **Data Validation:** Pydantic v2 & Pydantic-Settings
- **Environment Management:** python-dotenv

### Algorithms & Services (Phase 2 & Phase 3)
- Python Standard Library (`re`, `hashlib`, `json`, `enum`, `collections`)
- Deterministic SHA-256 fingerprinting and occurrence aggregation

### Quality & Testing
- **Test Framework:** pytest & pytest-cov (119 passing tests, 91% coverage)
- **Linter & Formatter:** Ruff

---

## 5. Installation & Quickstart

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

## 6. Implementation Roadmap

- [x] **Phase 1: Project Setup & Sample Logs**
  - Scaffolding, configuration management, and initial test suite.
- [x] **Phase 2: Core Log Parsing & Failure Detection**
  - Line-by-line parsing, level normalization, Python/Java tracebacks.
  - 1-based source line mapping.
- [x] **Phase 3: Failure Fingerprinting & Grouping**
  - Variable normalization (UUIDs, request IDs, hex addresses).
  - Deterministic SHA-256 fingerprinting.
  - Multi-occurrence failure grouping and recurrence metrics.
- [ ] **Phase 4: Input Validation & Evidence Integrity**
  - Request validation limits (size, lines) and bounded evidence extraction.
  - REST API (`/health`, `/api/v1/analyze`).
- [ ] **Phase 5: LLM Service & Report Generation**
  - Provider-agnostic LLM interface with strict evidence validation.
- [ ] **Phase 6: Streamlit Dashboard & Documentation**
  - Interactive web UI with side-by-side evidence inspection.

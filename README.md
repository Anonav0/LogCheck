# LogLens AI — AI-Assisted Application Log Analyzer

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/tested_with-pytest-0a9edc.svg)](https://docs.pytest.org/)

**LogLens AI** is an intelligent log analysis engine designed to help software engineers rapidly inspect application and test logs, isolate errors and exceptions, extract multiline stack traces, group recurring failures via deterministic fingerprinting, and generate actionable, evidence-backed debugging summaries using LLMs.

> [!NOTE]
> **Development Status: Phase 4 Completed (Input Validation & Evidence Integrity)**
> Strict pre-parse input limits (byte size, line count, line length), UTF-8 verification, canonical line-splitting semantics, post-analysis evidence integrity validation, and failure group/metric verification are fully implemented and verified. LLM integration, REST API endpoints, and Streamlit dashboard will be implemented in subsequent phases.

---

## 1. Problem Statement

Modern software applications and automated test suites generate verbose, noisy logs. When incidents or test suite failures occur:
- Developers must manually sift through thousands of lines to spot relevant errors.
- Raw log inputs can be corrupted, oversized, or contain malicious line lengths designed to cause denial of service.
- Discrepancies between log splitters and parsers cause "off-by-one" line numbering errors.
- Automated triage tools or LLM summarizers risk hallucinating nonexistent line numbers, mutating source lines, or reporting fabricated metrics if not verified against the original input.

**LogLens AI** addresses these challenges through a strict 3-tier safety architecture:
1. **Pre-Parse Input Validation:** Rejects empty, invalidly encoded, or oversized payloads before parsing begins, protecting computational resources.
2. **Deterministic Processing Pipeline:** Parses lines, preserves exact 1-based source line numbers, extracts complete stack traces, and fingerprints failures deterministically into recurring failure groups.
3. **Evidence Integrity Verification:** Verifies every line reference, raw line text, group occurrence mapping, and aggregate metric against the original source log before any result is trusted or returned.

---

## 2. Input Validation Architecture (Phase 4)

### Configurable Limits and Units

All input boundaries are enforced via `app/core/config.py` settings and configurable via `.env`:

| Setting | Type | Default | Unit | Description |
| :--- | :--- | :--- | :--- | :--- |
| `MAX_LOG_SIZE_BYTES` | `int` | `10,485,760` | Bytes (10 MB) | Maximum allowed UTF-8 encoded payload size. Multi-byte Unicode characters are measured by UTF-8 byte length, not string length. |
| `MAX_LOG_LINES` | `int` | `20,000` | Physical Lines | Maximum number of physical lines permitted in a single log payload. |
| `MAX_LOG_LINE_LENGTH` | `int` | `16,384` | Characters | Maximum character length of any single log line to guard against memory exhaustion. |
| `ALLOW_PARTIAL_ANALYSIS` | `bool` | `False` | Boolean | Whether to accept truncated analysis when limits are exceeded (defaults to strict rejection). |

### Canonical Line Splitting & Trailing Newline Policy

To eliminate line-number discrepancies across the pipeline, LogLens AI defines canonical line splitting via `app/utils/line_references.py:split_source_lines(text: str) -> list[str]`:
- Uses Python's standard `splitlines()`.
- Recognizes `\n`, `\r\n`, and `\r`.
- A file ending in a single trailing newline (`"line 1\nline 2\n"`) has exactly **2 lines**.
- Consecutive trailing newlines (`"line 1\n\n"`) represent distinct empty lines and have **2 lines** (line 1: `"line 1"`, line 2: `""`).
- Line indices are strictly **1-based** throughout parser, group occurrences, and integrity checks.

### Input Validation Errors vs. Parser Warnings

LogLens AI maintains a strict boundary between invalid input and benign malformed logs:

```
[ Raw Input ] ──> validate_log_input() ──┬──> Fails limit / encoding / empty ──> Raises InputValidationError (Halt)
                                         │
                                         └──> Valid input (even if noisy/unstructured)
                                                      │
                                                      ▼
                                                parse_log_text()
                                                      │
                                                      ├──> Corrupted timestamps: Kept, timestamp=raw, warning emitted
                                                      ├──> Truncated JSON lines: Kept as raw text, level=None/inferred
                                                      ├──> Legacy text/banners: Kept as LineCategory.UNKNOWN
                                                      └──> Non-fatal parse errors: Recorded in ParsingResult.warnings
```

- **Input Validation Errors (`InputValidationError`):** Raised when input cannot be safely processed (e.g., `EMPTY_LOG_INPUT`, `INVALID_ENCODING`, `LOG_TOO_LARGE`, `TOO_MANY_LOG_LINES`, `LOG_LINE_TOO_LONG`).
- **Parser Warnings:** Malformed timestamps (`2026-99-99 25:61:99`), broken JSON, and unrecognized formats remain processable and are retained without crashing.

---

## 3. Evidence Integrity Verification

Before any `ParsingResult` or `FailureAnalysisResult` is exposed to users or downstream LLM workflows, it is passed through `validate_parsing_result()` or `validate_analysis_result()`:

1. **Source Line Bounds:** Every line number $L$ in an entry or event must satisfy $1 \le L \le \text{total\_lines}$.
2. **Source Line Fidelity:** The `raw_line` content stored in the model must match `canonical_lines[L - 1]` character-for-character.
3. **Range Validity:** For every failure event, `start_line <= primary_line <= end_line`.
4. **Unique Event ID Association:** Each `failure_event_id` is unique and points to an existing event.
5. **Group Occurrences Consistency:**
   - Every group occurrence links to an existing failure event.
   - Group `occurrence_count == len(occurrences)`.
   - `first_seen_line == min(occurrences.primary_line)` and `last_seen_line == max(occurrences.primary_line)`.
   - Group `fingerprint` is verified to be a valid 64-character hex SHA-256 string.
6. **Aggregate Metrics Verification:**
   - `total_log_lines == parsing_result.total_lines`
   - `total_failure_events == sum(g.occurrence_count)`
   - `unique_failure_groups == len(failure_groups)`
   - `repeated_failure_groups == count(g where g.occurrence_count > 1)`
   - `most_frequent_failure_count == max(g.occurrence_count)`

If any check fails, `EvidenceIntegrityError` is raised (or an `EvidenceValidationResult` with `is_valid=False` and structured `ValidationIssue` items is returned).

---

## 4. End-to-End Validated Analysis Example

```python
from pathlib import Path
from app.services.evidence_validator import run_validated_analysis

log_text = Path("tests/fixtures/recurring_failures.log").read_text(encoding="utf-8")

# run_validated_analysis executes:
# 1. validate_log_input (byte, line, character limits, encoding)
# 2. parse_log_text (1-based entries, stack traces, failure events)
# 3. analyze_failures (fingerprinting, grouping, metrics)
# 4. validate_analysis_result (full evidence integrity verification)
analysis = run_validated_analysis(log_text)

print(f"Total lines verified: {analysis.metrics.total_log_lines}")
print(f"Unique failure groups: {analysis.metrics.unique_failure_groups}")
print(f"Repeated failures: {analysis.metrics.repeated_failure_events}")
```

### Representative Invalid-Input Validation Error Example

When an input violates configured safety boundaries:

```python
from app.core.exceptions import InputValidationError
from app.services.input_validator import validate_log_input

try:
    validate_log_input("   \n\n\t   ")
except InputValidationError as err:
    print(err.to_dict())
```

**Output:**
```json
{
  "code": "EMPTY_LOG_INPUT",
  "message": "Log input is empty or contains only whitespace.",
  "line_number": null,
  "limit": null,
  "actual": null
}
```

When a single line exceeds `MAX_LOG_LINE_LENGTH`:
```json
{
  "code": "LOG_LINE_TOO_LONG",
  "message": "Line 42 exceeds maximum allowed character length (16384 characters).",
  "line_number": 42,
  "limit": 16384,
  "actual": 25000
}
```

---

## 5. Security & Privacy Considerations

- **Diagnostics Safety:** Validation errors and issues return line numbers, counts, and limit definitions. They **never** include full submitted raw logs or sensitive tokens in exception messages to avoid accidental leaking in monitoring systems or HTTP error responses.
- **Resource Protection:** Payloads exceeding byte or line thresholds are rejected before invoking regex evaluators or JSON parsers, preventing Regular Expression Denial of Service (ReDoS) or memory exhaustion.

---

## 6. Known Limitations

- **Streaming / Chunked Logs:** Current validation processes complete in-memory strings or bytes. Streaming parsing for multi-gigabyte files is out of scope for the current phase.
- **Log Masking / Redaction:** Automatic redaction of credentials and PII within log lines will be coordinated with the LLM triage pipeline in Phase 5.

---

## 7. Technology Stack

### Backend & Core
- **Language:** Python 3.11+ (Tested on Python 3.12)
- **Data Validation:** Pydantic v2 & Pydantic-Settings
- **Environment Management:** python-dotenv

### Algorithms & Services
- Python Standard Library (`re`, `hashlib`, `json`, `enum`, `collections`)
- Deterministic SHA-256 failure fingerprinting and conservative variable normalization
- Dual-stage input and evidence integrity validators

### Quality & Testing
- **Test Framework:** pytest & pytest-cov (192 passing tests, 91% code coverage)
- **Linter & Formatter:** Ruff (100% compliant)

---

## 8. Installation & Verification

```bash
# Clone repository and enter directory
git clone <repo-url>
cd LogCheck

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run all 192 automated unit and integration tests
pytest

# Run tests with statement and branch coverage
pytest --cov=app --cov-report=term-missing

# Run code style and lint checks
ruff check .
ruff format --check .
```

---

## 9. Implementation Roadmap

- [x] **Phase 1: Project Setup & Sample Logs**
  - Scaffolding, configuration management, and initial test suite.
- [x] **Phase 2: Core Log Parsing & Failure Detection**
  - Line-by-line parsing, level normalization, Python/Java tracebacks.
  - 1-based source line mapping.
- [x] **Phase 3: Failure Fingerprinting & Grouping**
  - Variable normalization (UUIDs, request IDs, hex addresses).
  - Deterministic SHA-256 fingerprinting.
  - Multi-occurrence failure grouping and recurrence metrics.
- [x] **Phase 4: Input Validation & Evidence Integrity**
  - Strict pre-parse size, line-count, and line-length limits.
  - Canonical line splitting semantics (`split_source_lines`).
  - Evidence integrity verification on entries, events, groups, and metrics.
- [ ] **Phase 5: LLM Service & Report Generation**
  - Provider-agnostic LLM interface with strict evidence validation.
- [ ] **Phase 6: Streamlit Dashboard & REST API**
  - Interactive web UI with side-by-side evidence inspection.

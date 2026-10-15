# REST API Reference & Examples — LogLens AI

The LogLens AI backend is implemented with **FastAPI** and provides strictly typed REST endpoints with automatic OpenAPI documentation, request correlation headers, and standardized error envelopes.

Base URL: `http://127.0.0.1:8000`

---

## 1. Operational Probes

### Liveness Probe (`GET /health`)

Verifies that the API service process is active and accepting traffic. Does not make external network calls.

#### Request

```bash
curl -i http://127.0.0.1:8000/health
```

#### Response (`200 OK`)

```http
HTTP/1.1 200 OK
content-type: application/json
x-request-id: 3c9b8c0e-4a6f-4a37-9755-1f9e2b1049ad
x-process-time: 0.82ms

{
  "status": "ok",
  "service": "LogLens AI"
}
```

---

### Readiness Probe (`GET /health/ready`)

Reports whether the deterministic engine is operational and checks if LLM capabilities are configured. Evaluates configuration strictly offline without making external provider calls.

#### Request

```bash
curl -i http://127.0.0.1:8000/health/ready
```

#### Response (`200 OK`)

```json
{
  "status": "ready",
  "llm_enabled": false,
  "llm_available": false
}
```

---

## 2. Log Analysis (`POST /api/v1/analyze`)

Executes the complete log processing pipeline: input validation, multiline parsing, failure detection, SHA-256 fingerprinting, evidence integrity validation, and optional AI triage.

### Request Body Schema (`AnalyzeLogRequest`)

| Field        | Type      | Required | Default | Description                                                                  |
| :----------- | :-------- | :------: | :-----: | :--------------------------------------------------------------------------- |
| `log_text`   | `string`  | **Yes**  |    —    | Raw log content to analyze (1 to 1,048,576 UTF-8 bytes).                     |
| `include_ai` | `boolean` |    No    | `false` | When `true`, requests AI triage (or automatic fallback if disabled/offline). |

---

### Example A: Deterministic Analysis (`include_ai: false`)

#### Request

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "log_text": "2026-10-14 10:00:00 [ERROR] app.worker: DatabaseConnectionError: Lost connection to replica\n2026-10-14 10:00:02 [ERROR] app.worker: DatabaseConnectionError: Lost connection to replica",
    "include_ai": false
  }'
```

#### Response (`200 OK`)

```json
{
  "request_id": "8d3e9114-1e09-4bf9-8b01-52a106f3b0e3",
  "status": "completed",
  "metrics": {
    "total_log_lines": 2,
    "total_error_entries": 2,
    "total_warning_entries": 0,
    "total_failure_events": 2,
    "unique_failure_groups": 1,
    "repeated_failure_groups": 1,
    "repeated_failure_events": 2,
    "most_frequent_failure_count": 2
  },
  "failure_events": [
    {
      "event_id": "event-1",
      "start_line_number": 1,
      "end_line_number": 1,
      "severity": "ERROR",
      "exception_type": "DatabaseConnectionError",
      "message": "DatabaseConnectionError: Lost connection to replica",
      "stack_trace": [],
      "component": "app.worker"
    },
    {
      "event_id": "event-2",
      "start_line_number": 2,
      "end_line_number": 2,
      "severity": "ERROR",
      "exception_type": "DatabaseConnectionError",
      "message": "DatabaseConnectionError: Lost connection to replica",
      "stack_trace": [],
      "component": "app.worker"
    }
  ],
  "failure_groups": [
    {
      "fingerprint": "8b9a2c10398ef30948ab12e09348123049812349081234098123049812304981",
      "title": "DatabaseConnectionError: Lost connection to replica",
      "failure_category": "database_error",
      "occurrence_count": 2,
      "first_seen_line": 1,
      "last_seen_line": 2,
      "representative_message": "DatabaseConnectionError: Lost connection to replica",
      "component": "app.worker",
      "occurrences": [
        {
          "event_id": "event-1",
          "start_line_number": 1,
          "end_line_number": 1
        },
        {
          "event_id": "event-2",
          "start_line_number": 2,
          "end_line_number": 2
        }
      ]
    }
  ],
  "parser_warnings": [],
  "ai_analysis": null,
  "analysis_source": "none",
  "processing_time_ms": 2.14
}
```

---

### Example B: AI-Assisted Analysis with Fallback (`include_ai: true`)

When `include_ai: true` is requested and the LLM provider is disabled or offline, LogLens AI automatically completes analysis with `status="completed_with_fallback"`:

```json
{
  "request_id": "b3049812-76fa-49d8-9df2-421980ec9823",
  "status": "completed_with_fallback",
  "metrics": { "...": "..." },
  "failure_groups": ["..."],
  "ai_analysis": {
    "summary": "Deterministic log analysis completed. Detected 2 failure event(s) clustered into 1 distinct failure group(s) across 2 log lines.",
    "likely_causes": [
      {
        "description": "Recurring DatabaseConnectionError in app.worker (2 occurrences)",
        "reasoning": "First detected at line 1. Message: DatabaseConnectionError: Lost connection to replica",
        "evidence_refs": [
          {
            "line_number": 1,
            "excerpt": "Lost connection to replica"
          }
        ]
      }
    ],
    "recommended_actions": [
      {
        "action": "Investigate primary failure pattern: DatabaseConnectionError",
        "rationale": "Accounts for 2 of 2 total failure event(s).",
        "priority": "high",
        "evidence_refs": [
          {
            "line_number": 1,
            "excerpt": "Lost connection to replica"
          }
        ]
      }
    ],
    "confidence": 0.5,
    "limitations": [
      "AI assistance is disabled or offline; insights were generated deterministically."
    ]
  },
  "analysis_source": "fallback",
  "processing_time_ms": 2.85
}
```

---

## 3. Standardized Error Responses

All API errors return an envelope matching the Pydantic `ErrorResponse` schema:

```json
{
  "error": {
    "code": "MACHINE_READABLE_CODE",
    "message": "Sanitized, human-readable error description",
    "request_id": "unique-uuid",
    "line_number": null,
    "limit": null,
    "actual": null
  }
}
```

### Error Case 1: Malformed JSON (`400 Bad Request`)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{ invalid json content '
```

```json
{
  "error": {
    "code": "MALFORMED_JSON",
    "message": "Malformed JSON request body: Invalid JSON format.",
    "request_id": "f512da34-9214-41b2-9a3b-214098ec9821",
    "line_number": null,
    "limit": null,
    "actual": null
  }
}
```

### Error Case 2: Oversized Log Payload (`413 Content Too Large`)

When log payload exceeds 1,048,576 bytes:

```json
{
  "error": {
    "code": "LOG_TOO_LARGE",
    "message": "Log payload size (1,050,000 bytes) exceeds maximum permitted limit (1,048,576 bytes).",
    "request_id": "9a21804e-41bc-4019-9fa1-019284019823",
    "line_number": null,
    "limit": 1048576,
    "actual": 1050000
  }
}
```

### Error Case 3: Empty / Whitespace Input (`422 Unprocessable Content`)

```json
{
  "error": {
    "code": "EMPTY_LOG_INPUT",
    "message": "Log content cannot be empty or contain only whitespace.",
    "request_id": "31489021-9fa1-4190-b182-901823901823",
    "line_number": null,
    "limit": null,
    "actual": null
  }
}
```

### Error Case 4: Schema Validation (`422 Unprocessable Content`)

When unexpected or wrong typed fields are passed (enforced by `extra="forbid"`):

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Field 'unknown_field' is not permitted.",
    "request_id": "10928340-fa19-41b2-8921-901823901823",
    "line_number": null,
    "limit": null,
    "actual": null
  }
}
```

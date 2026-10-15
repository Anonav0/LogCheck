# Sample Walkthrough: Recurring Failures Triage

This walkthrough demonstrates how LogLens AI processes a real application log, clusters recurring exceptions into deterministic groups, preserves exact source line numbers, and presents actionable triage insights.

---

## 1. Selected Fixture: `recurring_failures.log`

We use the bundled test fixture [`tests/fixtures/recurring_failures.log`](../tests/fixtures/recurring_failures.log) (34 lines, 2.3 KB).

### Raw Fixture Excerpt

```text
2026-10-14 09:15:01,001 [INFO] app.gateway: Received request req-a1b2c3d4 for /api/v1/users/42
2026-10-14 09:15:01,120 [ERROR] app.gateway: Failed processing request req-a1b2c3d4: DatabaseConnectionError: Connection lost to database cluster primary
Traceback (most recent call last):
  File "/app/services/gateway.py", line 142, in handle_request
    return user_service.get_user(user_id)
  File "/app/services/user_service.py", line 88, in get_user
    return db_pool.acquire()
DatabaseConnectionError: Connection lost to database cluster primary
2026-10-14 09:15:02,000 [INFO] app.gateway: Received request req-e5f6g7h8 for /api/v1/orders/99
2026-10-14 09:15:02,450 [ERROR] app.gateway: Failed processing request req-e5f6g7h8: ServiceUnavailable: Upstream payment service timed out
...
```

---

## 2. Running the Analysis

### Via the Streamlit Web Console

1. Launch the application:
   ```bash
   ./run_app.sh
   ```
2. In the left sidebar, choose **Input Mode** -> **Sample Logs**.
3. Select `recurring_failures.log` from the dropdown. The log content will load into view.
4. Leave **Request AI Assistance** checked (or toggle it off to test deterministic analysis).
5. Click **🚀 Analyze Logs**.

### Via the REST API (`curl`)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "log_text": "'"$(cat tests/fixtures/recurring_failures.log | sed 's/"/\\"/g' | awk '{printf "%s\\n", $0}')"'",
    "include_ai": false
  }' | jq .
```

---

## 3. Interpreting the Results

### A. Deterministic Metrics & Frequency

The API calculates aggregate metrics over the entire submitted log:

- **Total Log Lines:** `34`
- **Total Failure Events:** `4`
- **Unique Failure Groups:** `2`
- **Repeated Failure Groups:** `2` (both groups recur multiple times)
- **Most Frequent Failure Count:** `2`

### B. Recurring Failure Groups

LogLens AI clusters the 4 individual failure events into **2 distinct groups** using SHA-256 fingerprinting:

#### Group 1: `DatabaseConnectionError` (Rank 1 — Most Frequent)

- **Recurrence Count:** 2 occurrences
- **First Seen Line:** Line 2 (Exception at Line 8)
- **Last Seen Line:** Line 17 (Exception at Line 23)
- **Representative Message:** `DatabaseConnectionError: Connection lost to database cluster primary`
- **Component:** `app.gateway`
- **Stack Trace:**
  ```python
  File "/app/services/gateway.py", line 142, in handle_request
    return user_service.get_user(user_id)
  File "/app/services/user_service.py", line 88, in get_user
    return db_pool.acquire()
  ```

#### Group 2: `ServiceUnavailable` (Rank 2)

- **Recurrence Count:** 2 occurrences
- **First Seen Line:** Line 10 (Exception at Line 14)
- **Last Seen Line:** Line 25 (Exception at Line 31)
- **Representative Message:** `ServiceUnavailable: Upstream payment service timed out`

---

## 4. Source Line Tracing & Evidence Verification

Every failure is mapped to exact 1-based source lines:

1. In the **📜 Source Line Viewer** tab:
   - Line 8 and Line 23 are highlighted in **Red** (`rgba(230, 57, 70, 0.28)`) as primary failure occurrences.
   - Lines 3–7 and Lines 18–22 are highlighted in **Orange** as supporting stack trace context.
2. Clicking an occurrence automatically centers the view around that occurrence's line number with a $\pm 5$ line radius.

---

## 5. AI Assistance vs. Deterministic Fallback

### Scenario 1: AI Assistance Disabled or Provider Offline (`LLM_ENABLED=false`)

When an external LLM is disabled or unavailable, LogLens AI automatically synthesizes a **Deterministic Fallback Report**:

```json
{
  "status": "completed_with_fallback",
  "analysis_source": "fallback",
  "ai_analysis": {
    "summary": "Deterministic log analysis completed. Detected 4 failure event(s) clustered into 2 distinct failure group(s) across 34 log lines.",
    "likely_causes": [
      {
        "description": "Recurring DatabaseConnectionError in app.gateway (2 occurrences)",
        "reasoning": "First detected at line 2. Message: DatabaseConnectionError: Connection lost to database cluster primary",
        "evidence_refs": [
          {
            "line_number": 2,
            "excerpt": "Failed processing request req-a1b2c3d4"
          }
        ]
      }
    ],
    "recommended_actions": [
      {
        "action": "Investigate primary failure pattern: DatabaseConnectionError",
        "rationale": "Accounts for 2 of 4 total failure event(s).",
        "priority": "high",
        "evidence_refs": [
          {
            "line_number": 2,
            "excerpt": "Failed processing request req-a1b2c3d4"
          }
        ]
      }
    ],
    "confidence": 0.5,
    "limitations": [
      "AI assistance is disabled or offline; insights were generated deterministically."
    ]
  }
}
```

### Scenario 2: AI Assistance Enabled (`LLM_ENABLED=true`)

When configured with a valid provider (e.g., Google Gemini or OpenAI):

- LogLens AI constructs a bounded prompt containing the group summary and sanitized excerpts.
- Secrets (`sk-...`, Bearer tokens, passwords) are automatically redacted.
- The model returns a structured JSON triage report with a confidence score ($\ge 0.90$) and verified citations pointing to Line 8 and Line 14.
- If the model references a line that doesn't exist, LogLens AI immediately rejects the output and returns the deterministic fallback above.

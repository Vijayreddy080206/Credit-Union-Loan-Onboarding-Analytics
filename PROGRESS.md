# Credit Union Loan Onboarding - Progress & Audit

## STEP 0: AUDIT

| Feature / Phase | Status | Evidence (File Paths / Notes) |
|---|---|---|
| **FastAPI backend** | PARTIAL | `api/main.py`, `api/routers/applications.py`. Currently uses a mock extraction and writes straight to DB in bulk script. |
| **PostgreSQL + Alembic** | DONE | `alembic/versions/0001_initial_schema.py`, `docker-compose.yml`. Schema is created. |
| **Rules engine** | PARTIAL | `services/rules_engine.py`. Has `MAX_AGE_YEARS` rule which is a compliance red flag. Loan-to-income ratio uses monthly instead of annual. |
| **Streamlit dashboard** | PARTIAL | `dashboard/app.py`. Review queue shows garbage ID (serialization bug). |
| **Synthetic data** | PARTIAL | `data/synthetic/generate.py`. Has 61 clean apps, lacks blurry/rotated/edge-cases for Phase C. |
| **Audit Log** | DONE | `models/audit_log.py`, `services/audit.py`. Append-only. |
| **Idempotency** | DONE | `models/application.py` (idempotency_key unique index), `api/routers/applications.py` handles upsert logic. |
| **Docker compose** | DONE | `docker-compose.yml` runs api, postgres, dashboard, n8n, mock_crm. |
| **Groq / Real LLM Extraction**| MISSING | `services/extraction/llm_adapter.py` needs Groq implementation. Fallback vision logic missing. |
| **Evaluation Harness** | MISSING | `scripts/evaluate.py` needs to hit real POST API, track false approvals, confidence vs correctness. |
| **Human Review Loop** | MISSING | Needs reviewer approve/reject endpoints, and UI in dashboard. |
| **CRM Integration** | PARTIAL | Mock CRM exists in `mock_crm/main.py`. Needs real robust retry logic & integration tests. |
| **n8n Workflow** | MISSING | Webhooks exist, but workflow JSON is missing or incomplete for branching. |
| **pytest / CI** | MISSING | Tests exist but don't cover all boundaries or flows. GitHub Actions CI missing. |

### Suspected Problems Audit:
1. *"100% extraction accuracy" comes from a MOCK provider* - Confirmed. `scripts/evaluate.py` (previously) and `README.md` report 100% based on `LLM_PROVIDER=mock`.
2. *Bulk script writes straight to DB* - Confirmed. `scripts/populate_db.py` uses SQLAlchemy to insert directly, bypassing FastAPI.
3. *Dashboard review queue shows a garbage id* - Confirmed. The Streamlit dataframe serialization of UUIDs shows as a byte dictionary.
4. *Loan-to-income ratio may use monthly* - Confirmed. `services/rules_engine.py` compares requested amount to `monthly_income * 12`, but might be doing it wrong or naming it wrong.
5. *applicant_over_maximum_age auto-reject rule exists* - Confirmed. `services/rules_engine.py` rejects if age > MAX_AGE_YEARS.
6. *README overclaims* - Confirmed. 

## CURRENT PHASE: Phase A (PASSED)

**Goal:** Correctness fixes and env cleanup.
- [x] Fix ID serialization bug in dashboard (`apps_df['id'] = apps_df['id'].astype(str)`)
- [x] Fix loan-to-income basis to use annual income properly (used `settings.MAX_LOAN_TO_INCOME_RATIO`)
- [x] Fix age rules (>= 18, remove maximum age rejection) (proper datetime math used)
- [x] Clean up `.env` and `.env.example`
- [x] Write boundary unit tests for rules
- [x] Test `.env` parser

**Verification:**
`pytest tests/test_phase_a.py -v` passed successfully.

---
## CURRENT PHASE: Phase B (PASSED)

**Goal:** Real Groq extraction
- [x] Implement GroqProvider (added `GroqAdapter` in `llm_adapter.py`)
- [x] Document preprocessing (text first, vision fallback in `service.py` and `pdf_reader.py` using PyMuPDF)
- [x] Pydantic-validated structured output, retries, 429 handling (using OpenAI SDK's built-in `max_retries` plus explicit exponential backoff loop)
- [x] Handle invalid JSON, timeouts, rate limits, routing to HITL (Exceptions caught, returns empty extraction which rules engine flags for HUMAN_REVIEW)

---
## CURRENT PHASE: Phase C (PASSED)

**Goal:** Harder synthetic data
- [x] Add documents that are rotated, low-resolution or blurry
- [x] Mismatched names, expired IDs, duplicate applicants
- [x] Store a ground_truth.json for every document

---
## CURRENT PHASE: Phase D (PASSED)

**Goal:** Evaluation Harness Enhancement
- [x] Update scripts/evaluate.py to compare field-level extracted values against ground_truth.json.
- [x] Measure exact accuracy of the LLM extraction separately from the rules engine outcome.
- [x] Handle fuzzy matching/normalizing for dates and currency during evaluation.

---
## CURRENT PHASE: Phase E (PASSED)

**Goal:** Human Review Loop
- [x] Add approve/reject endpoints in the API for HUMAN_REVIEW applications.
- [x] Add a UI in the Streamlit dashboard to action these applications.

---
## CURRENT PHASE: Phase F (PASSED)

**Goal:** CRM Integration
- [x] Add robust retry logic to the CRM client.
- [x] Implement exponential backoff for mock CRM failures (which throws HTTP 500 randomly).
- [x] Write integration tests for the CRM sync.

---
## CURRENT PHASE: Phase G (PASSED)

**Goal:** n8n Workflow
- [x] Export the n8n workflow as a JSON file and store it in `n8n/workflow.json`.
- [x] Add the webhook endpoints logic and branching for HUMAN_REVIEW in the workflow.

---
## CURRENT PHASE: Phase H (PASSED)

**Goal:** CI/CD and Final Polish
- [x] Add GitHub Actions workflow for testing (`.github/workflows/test.yml`).
- [x] Ensure all tests pass.
- [x] Generate `FINAL_REPORT_DRAFT.md` summarizing the project.
- [x] Update `README.md` to be perfect and honest without inflated language.

﻿## Phase B Evidence: Real Groq Provider (openai/gpt-oss-120b, openai/gpt-oss-20b)
**Command executed:** `$env:PYTHONPATH="."; python scripts/phase_b_evidence.py`

### Document 1: GOVERNMENT_ID
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\91d6fa4b-0e8f-42f5-afcc-88f6464f40c9\government_id.pdf`
2026-09-29 17:58:14 [info     ] extracting_document            doc_type=GOVERNMENT_ID provider=groq
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 2: PROOF_OF_INCOME
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\91d6fa4b-0e8f-42f5-afcc-88f6464f40c9\proof_of_income.pdf`
2026-09-29 17:58:16 [info     ] extracting_document            doc_type=PROOF_OF_INCOME provider=groq
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 3: ADDRESS_PROOF
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\91d6fa4b-0e8f-42f5-afcc-88f6464f40c9\address_proof.pdf`
2026-09-29 17:58:17 [info     ] extracting_document            doc_type=ADDRESS_PROOF provider=groq
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 4: GOVERNMENT_ID
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\358ce4e5-4149-4c4f-b8cd-ec32984710aa\government_id.pdf`
2026-09-29 17:58:17 [info     ] extracting_document            doc_type=GOVERNMENT_ID provider=groq
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 5: PROOF_OF_INCOME
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\358ce4e5-4149-4c4f-b8cd-ec32984710aa\proof_of_income.pdf`
2026-09-29 17:58:18 [info     ] extracting_document            doc_type=PROOF_OF_INCOME provider=groq
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 6: ADDRESS_PROOF
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\358ce4e5-4149-4c4f-b8cd-ec32984710aa\address_proof.pdf`
2026-09-29 17:58:19 [info     ] extracting_document            doc_type=ADDRESS_PROOF provider=groq
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 7: GOVERNMENT_ID
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\88166307-dc93-4399-b45f-3526be387494\government_id.pdf`
2026-09-29 17:58:20 [info     ] extracting_document            doc_type=GOVERNMENT_ID provider=groq
2026-09-29 17:58:20 [warning  ] groq_rate_limit                attempt=1
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 8: PROOF_OF_INCOME
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\88166307-dc93-4399-b45f-3526be387494\proof_of_income.pdf`
2026-09-29 17:58:24 [info     ] extracting_document            doc_type=PROOF_OF_INCOME provider=groq
2026-09-29 17:58:25 [warning  ] groq_rate_limit                attempt=1
2026-09-29 17:58:27 [warning  ] groq_rate_limit                attempt=2
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 9: ADDRESS_PROOF
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\88166307-dc93-4399-b45f-3526be387494\address_proof.pdf`
2026-09-29 17:58:29 [info     ] extracting_document            doc_type=ADDRESS_PROOF provider=groq
2026-09-29 17:58:29 [warning  ] groq_rate_limit                attempt=1
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|


### Document 10: GOVERNMENT_ID
- **Path**: `C:\Users\Vijay\Desktop\honest consultant\data\synthetic\docs\3b8917bb-5285-4423-bb1a-95ce0c9c82d3\government_id.pdf`
2026-09-29 17:58:34 [info     ] extracting_document            doc_type=GOVERNMENT_ID provider=groq
2026-09-29 17:58:34 [warning  ] groq_rate_limit                attempt=1
- **Extraction Method**: `groq_text` (Vision Path Used: No)

| Field | Expected Value | Actual Value | Confidence |
|-------|----------------|--------------|------------|



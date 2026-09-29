# Loan Onboarding Analytics - Final Engineering Report

This report summarizes the remediation, bug fixes, and architectural improvements applied to the Credit Union Loan Onboarding project. The initial state of the project possessed significant logic gaps, "happy path" assumptions, and lacked robustness. 

## 1. LLM Extraction & Rate Limiting (Phase B)
- **Real Groq Implementation**: Replaced the "100% accurate" mock extraction with a real integration to the Groq API. We mapped `DocumentType` to two distinct models: `openai/gpt-oss-120b` for text-based analysis and `openai/gpt-oss-20b` for vision-based fallback (using `base64` encoded images).
- **Rate Limit & Retry Handling**: Replaced generic retries with a custom exponential backoff mechanism that strictly honors the `Retry-After` HTTP header from the Groq API, addressing the `429 Too Many Requests` limit organically.
- **Graceful Degradation**: If extraction fails entirely (e.g., after 5 rate-limit retries or malformed JSON responses), the system flags the extraction as a failure instead of crashing, routing the application to `HUMAN_REVIEW` via the rules engine.

## 2. Deterministic Rules Engine (Phase A)
- **Compliance Bugs Fixed**: Removed the illegal `applicant_over_maximum_age` rule. Repaired the ID expiry logic to enforce a 30-day buffer period (`ID_EXPIRY_BUFFER_DAYS`).
- **Calculation Bug**: Fixed the loan-to-income ratio check to correctly multiply the monthly income by 12, evaluating the ratio against annual income as defined in `MAX_LOAN_TO_INCOME_RATIO`.

## 3. Workflow Orchestration & Human Review (Phases E & G)
- **n8n Workflow**: Created a declarative workflow definition (`n8n/workflow.json`) mimicking the external orchestration that routes webhooks based on the decision (`AUTO_APPROVED`, `AUTO_REJECTED`, or `HUMAN_REVIEW`).
- **Manual Review Endpoints**: Implemented `/applications/{app_id}/approve` and `/applications/{app_id}/reject` endpoints to permit secure human overrides on flagged applications.
- **Dashboard UI**: Added an interactive interface in the Streamlit dashboard for humans to review the queue, submit review notes, and trigger the endpoints. Fixed a pre-existing UUID serialization bug that displayed byte dicts in the dataframe.

## 4. CRM Integration (Phase F)
- **Robust Mock CRM Sync**: Integrated `tenacity` into the CRM synchronization flow. The client now leverages exponential backoff and jitter to overcome transient HTTP 500 errors from the mock CRM without failing the upstream pipeline.
- **Test Coverage**: Created integration tests asserting that repeated sync failures eventually succeed on retry, or gracefully return `False` after exhausting attempts.

## 5. Synthetic Data & Evaluation Harness (Phases C & D)
- **Complex Data Generation**: Overhauled `data/synthetic/generate.py` to generate explicit edge cases, including blurry documents (`LOW_CONFIDENCE`), duplicated applications, rotated scans, and borderline income numbers.
- **Ground Truth Storage**: The synthetic generator now saves a `ground_truth.json` alongside every generated applicant PDF, containing the exact values created by `Faker`.
- **Field-Level Evaluation**: Rewrote `scripts/evaluate.py` to compare the LLM's extracted response against the explicit `ground_truth.json` field-by-field, measuring the precise accuracy of the OCR/LLM step independently from the final rules engine decision.

## 6. CI/CD (Phase H)
- **GitHub Actions**: Configured `.github/workflows/test.yml` to automatically run `pytest` and generate coverage reports on all pushes and PRs to `main`.
- **Test Suite Completeness**: Achieved high coverage by implementing edge cases (age bounds, retry logic) inside `pytest`. All tests are currently passing in the suite.

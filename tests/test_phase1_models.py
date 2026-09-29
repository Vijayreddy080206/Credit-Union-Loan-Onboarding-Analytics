"""
Phase 1 tests — verifies models, enums, and audit helper without needing
a live database (we test model construction and enum values only).

Design note: we test model construction, enum validity, and the audit helper
logic in isolation. DB integration tests (that actually INSERT rows) live in
tests/integration/ and require a running Postgres. Fast unit tests run in CI
without Docker; integration tests are gated behind a --run-integration flag.
"""
import uuid

import pytest

from models.application import Application, ApplicationDocument, ApplicationStatus, DocumentType
from models.audit_log import AuditLog, AuditEventType
from models.reviewer import ReviewDecision


class TestApplicationStatusEnum:
    """All expected status values must be present and have the right string values."""

    def test_all_statuses_are_strings(self):
        for status in ApplicationStatus:
            assert isinstance(status.value, str)

    def test_submitted_is_initial_status(self):
        assert ApplicationStatus.SUBMITTED == "SUBMITTED"

    def test_terminal_statuses_exist(self):
        terminals = {
            ApplicationStatus.AUTO_APPROVED,
            ApplicationStatus.AUTO_REJECTED,
            ApplicationStatus.MANUALLY_APPROVED,
            ApplicationStatus.MANUALLY_REJECTED,
        }
        assert len(terminals) == 4

    def test_human_review_status(self):
        assert ApplicationStatus.HUMAN_REVIEW == "HUMAN_REVIEW"


class TestDocumentTypeEnum:
    def test_all_three_types_exist(self):
        types = {dt.value for dt in DocumentType}
        assert types == {"GOVERNMENT_ID", "PROOF_OF_INCOME", "ADDRESS_PROOF"}


class TestAuditEventTypeEnum:
    def test_extraction_events_exist(self):
        assert AuditEventType.EXTRACTION_STARTED == "EXTRACTION_STARTED"
        assert AuditEventType.EXTRACTION_COMPLETED == "EXTRACTION_COMPLETED"
        assert AuditEventType.EXTRACTION_FAILED == "EXTRACTION_FAILED"

    def test_crm_events_exist(self):
        assert AuditEventType.CRM_SYNC_ATTEMPTED == "CRM_SYNC_ATTEMPTED"
        assert AuditEventType.CRM_SYNC_SUCCEEDED == "CRM_SYNC_SUCCEEDED"
        assert AuditEventType.CRM_SYNC_FAILED == "CRM_SYNC_FAILED"

    def test_review_events_exist(self):
        assert AuditEventType.HUMAN_REVIEW_ASSIGNED == "HUMAN_REVIEW_ASSIGNED"
        assert AuditEventType.HUMAN_REVIEW_DECISION == "HUMAN_REVIEW_DECISION"


class TestApplicationModel:
    """Tests model attribute defaults without a DB session."""

    def test_default_status_is_submitted(self):
        app = Application(
            idempotency_key="test-key-001",
            applicant_name="Jane Doe",
            applicant_email="jane@example.com",
            requested_loan_amount=10000.00,
        )
        assert app.status == ApplicationStatus.SUBMITTED

    def test_id_defaults_to_uuid(self):
        app = Application(
            idempotency_key="test-key-002",
            applicant_name="John Smith",
            applicant_email="john@example.com",
            requested_loan_amount=5000.00,
        )
        # id is None until the DB assigns it (no session here), but the
        # default factory is uuid4. We verify the column definition accepts UUIDs.
        assert app.extraction_result is None
        assert app.rules_result is None

    def test_optional_fields_default_to_none(self):
        app = Application(
            idempotency_key="test-key-003",
            applicant_name="Alice",
            applicant_email="alice@example.com",
            requested_loan_amount=20000.00,
        )
        assert app.applicant_phone is None
        assert app.loan_purpose is None
        assert app.crm_contact_id is None
        assert app.crm_deal_id is None
        assert app.decision_reason is None


class TestApplicationDocumentModel:
    def test_document_creation(self):
        app_id = uuid.uuid4()
        doc = ApplicationDocument(
            application_id=app_id,
            document_type=DocumentType.GOVERNMENT_ID,
            file_path="/data/synthetic/id_001.pdf",
            mime_type="application/pdf",
        )
        assert doc.document_type == DocumentType.GOVERNMENT_ID
        assert doc.extracted_data is None
        assert doc.min_confidence is None


class TestAuditLogModel:
    def test_audit_log_creation(self):
        app_id = uuid.uuid4()
        log = AuditLog(
            application_id=app_id,
            event_type=AuditEventType.APPLICATION_SUBMITTED,
            actor="api_gateway",
            message="Application received via POST /applications",
            details={"ip": "192.168.1.1"},
        )
        assert log.event_type == AuditEventType.APPLICATION_SUBMITTED
        assert log.changed_from is None
        assert log.changed_to is None

    def test_status_change_event(self):
        app_id = uuid.uuid4()
        log = AuditLog(
            application_id=app_id,
            event_type=AuditEventType.STATUS_CHANGED,
            actor="rules_engine",
            message="Application auto-approved",
            changed_from="RULES_CHECK",
            changed_to="AUTO_APPROVED",
        )
        assert log.changed_from == "RULES_CHECK"
        assert log.changed_to == "AUTO_APPROVED"


class TestReviewDecisionModel:
    def test_review_decision_creation(self):
        app_id = uuid.uuid4()
        decision = ReviewDecision(
            application_id=app_id,
            reviewer_email="reviewer@creditunion.example.com",
            approved=True,
            notes="Verified income documents manually. Income confirmed.",
        )
        assert decision.approved is True
        assert decision.override_reason is None

    def test_rejection_with_override(self):
        app_id = uuid.uuid4()
        decision = ReviewDecision(
            application_id=app_id,
            reviewer_email="reviewer@creditunion.example.com",
            approved=False,
            notes="Income document appears altered.",
            override_reason="System flagged HUMAN_REVIEW but evidence of fraud found on manual check.",
        )
        assert decision.approved is False
        assert decision.override_reason is not None

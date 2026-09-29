"""
Phase 4 Tests — Rules Engine
"""
from datetime import date, timedelta
import pytest
from models.application import Application, ApplicationStatus
from schemas.extraction import (
    ApplicationExtractionResult, GovernmentIDExtraction,
    ProofOfIncomeExtraction, FieldResult
)
from services.rules_engine import rules_engine

@pytest.fixture
def base_application():
    return Application(
        applicant_name="John Doe",
        applicant_email="john@example.com",
        requested_loan_amount=5000.0,
        loan_purpose="Test"
    )

@pytest.fixture
def clean_extraction():
    return ApplicationExtractionResult(
        government_id=GovernmentIDExtraction(
            full_name=FieldResult(value="John Doe", confidence=0.95),
            date_of_birth=FieldResult(value="1990-01-01", confidence=0.95),
            id_number=FieldResult(value="ID-123", confidence=0.95),
            expiry_date=FieldResult(value="2030-01-01", confidence=0.95),
        ),
        proof_of_income=ProofOfIncomeExtraction(
            monthly_income=FieldResult(value="5000.00", confidence=0.95),
            annual_income=FieldResult(value="60000.00", confidence=0.95),
        ),
        overall_min_confidence=0.95
    )

def test_auto_approve(base_application, clean_extraction):
    result = rules_engine.evaluate(base_application, clean_extraction)
    assert result.decision == ApplicationStatus.AUTO_APPROVED

def test_reject_underage(base_application, clean_extraction):
    # Set age to 17
    dob = date.today() - timedelta(days=365 * 17)
    clean_extraction.government_id.date_of_birth.value = dob.isoformat()
    result = rules_engine.evaluate(base_application, clean_extraction)
    assert result.decision == ApplicationStatus.AUTO_REJECTED
    assert result.rejection_reason == "applicant_under_minimum_age"

def test_reject_expired_id(base_application, clean_extraction):
    expiry = date.today() - timedelta(days=1)
    clean_extraction.government_id.expiry_date.value = expiry.isoformat()
    result = rules_engine.evaluate(base_application, clean_extraction)
    assert result.decision == ApplicationStatus.AUTO_REJECTED
    assert result.rejection_reason == "government_id_expired"

def test_reject_low_income(base_application, clean_extraction):
    clean_extraction.proof_of_income.monthly_income.value = "1000.00"
    result = rules_engine.evaluate(base_application, clean_extraction)
    assert result.decision == ApplicationStatus.AUTO_REJECTED
    assert result.rejection_reason == "monthly_income_below_minimum"

def test_human_review_name_mismatch(base_application, clean_extraction):
    clean_extraction.government_id.full_name.value = "Jane Doe"
    result = rules_engine.evaluate(base_application, clean_extraction)
    assert result.decision == ApplicationStatus.HUMAN_REVIEW
    assert "name_mismatch" in result.flags

def test_human_review_low_confidence(base_application, clean_extraction):
    clean_extraction.overall_min_confidence = 0.5
    result = rules_engine.evaluate(base_application, clean_extraction)
    assert result.decision == ApplicationStatus.HUMAN_REVIEW
    assert "low_extraction_confidence" in result.flags

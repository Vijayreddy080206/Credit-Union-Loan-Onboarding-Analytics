import os
import pytest
from core.config import settings

def test_env_parsing():
    assert settings.LLM_PROVIDER == "groq"
    
from datetime import date, timedelta
from models.application import Application, ApplicationStatus
from schemas.extraction import ApplicationExtractionResult, FieldResult, GovernmentIDExtraction, ProofOfIncomeExtraction
from services.rules_engine import rules_engine

def test_rule_boundary_age():
    app = Application(requested_loan_amount=5000, applicant_name="Test")
    
    def get_ext(dob: str):
        ext = ApplicationExtractionResult()
        ext.government_id = GovernmentIDExtraction(
            full_name=FieldResult(value="Test", confidence=1.0),
            date_of_birth=FieldResult(value=dob, confidence=1.0),
            expiry_date=FieldResult(value=(date.today() + timedelta(days=100)).isoformat(), confidence=1.0)
        )
        ext.proof_of_income = ProofOfIncomeExtraction(
            employee_name=FieldResult(value="Test", confidence=1.0),
            employer=FieldResult(value="Inc", confidence=1.0),
            monthly_income=FieldResult(value="5000", confidence=1.0)
        )
        ext.overall_min_confidence = 1.0
        return ext

    today = date.today()
    # Exactly 18th birthday
    dob_18_exact = date(today.year - 18, today.month, today.day).isoformat()
    res = rules_engine.evaluate(app, get_ext(dob_18_exact))
    assert res.decision == ApplicationStatus.AUTO_APPROVED

    # Day before 18th birthday (still 17)
    dob_17_almost = (date(today.year - 18, today.month, today.day) + timedelta(days=1)).isoformat()
    res = rules_engine.evaluate(app, get_ext(dob_17_almost))
    assert res.decision == ApplicationStatus.AUTO_REJECTED
    assert res.rejection_reason == "applicant_under_minimum_age"

def test_rule_boundary_ratio_and_income():
    # 5000 monthly = 60000 annual
    # loan = 300000 -> ratio exactly 5.0
    app_good = Application(requested_loan_amount=300000, applicant_name="Test")
    app_bad = Application(requested_loan_amount=300001, applicant_name="Test")
    
    def get_ext(monthly_inc="5000", conf=1.0):
        ext = ApplicationExtractionResult()
        ext.government_id = GovernmentIDExtraction(
            full_name=FieldResult(value="Test", confidence=conf),
            date_of_birth=FieldResult(value="1990-01-01", confidence=conf),
            expiry_date=FieldResult(value=(date.today() + timedelta(days=100)).isoformat(), confidence=conf)
        )
        ext.proof_of_income = ProofOfIncomeExtraction(
            employee_name=FieldResult(value="Test", confidence=conf),
            employer=FieldResult(value="Inc", confidence=conf),
            monthly_income=FieldResult(value=monthly_inc, confidence=conf)
        )
        ext.overall_min_confidence = conf
        return ext
    
    # Exactly 5.0 ratio -> pass
    res = rules_engine.evaluate(app_good, get_ext("5000"))
    assert res.decision == ApplicationStatus.AUTO_APPROVED
    
    # Exceeds 5.0 ratio -> fail
    res = rules_engine.evaluate(app_bad, get_ext("5000"))
    assert res.decision == ApplicationStatus.AUTO_REJECTED
    assert res.rejection_reason == "loan_exceeds_income_ratio"

    # Min income boundary (assuming MIN_MONTHLY_INCOME is 1500)
    app_small = Application(requested_loan_amount=5000, applicant_name="Test")
    res = rules_engine.evaluate(app_small, get_ext("1500"))
    assert res.decision == ApplicationStatus.AUTO_APPROVED
    
    res = rules_engine.evaluate(app_small, get_ext("1499.99"))
    assert res.decision == ApplicationStatus.AUTO_REJECTED
    assert res.rejection_reason == "monthly_income_below_minimum"

    # Confidence exactly 0.80 (assuming CONFIDENCE_THRESHOLD is 0.8)
    res = rules_engine.evaluate(app_small, get_ext("1500", 0.80))
    assert res.decision == ApplicationStatus.AUTO_APPROVED
    
    res = rules_engine.evaluate(app_small, get_ext("1500", 0.79))
    assert res.decision == ApplicationStatus.HUMAN_REVIEW
    assert "low_extraction_confidence" in res.flags

def test_rule_boundary_id_expiry():
    app = Application(requested_loan_amount=5000, applicant_name="Test")
    
    def get_ext(days_to_expire: int):
        ext = ApplicationExtractionResult()
        ext.government_id = GovernmentIDExtraction(
            full_name=FieldResult(value="Test", confidence=1.0),
            date_of_birth=FieldResult(value="1990-01-01", confidence=1.0),
            expiry_date=FieldResult(value=(date.today() + timedelta(days=days_to_expire)).isoformat(), confidence=1.0)
        )
        ext.proof_of_income = ProofOfIncomeExtraction(
            employee_name=FieldResult(value="Test", confidence=1.0),
            employer=FieldResult(value="Inc", confidence=1.0),
            monthly_income=FieldResult(value="5000", confidence=1.0)
        )
        ext.overall_min_confidence = 1.0
        return ext

    # 31 days -> pass
    res = rules_engine.evaluate(app, get_ext(31))
    assert res.decision == ApplicationStatus.AUTO_APPROVED

    # 30 days -> exactly at buffer -> pass (since expiry < today + 30 is the rejection condition)
    res = rules_engine.evaluate(app, get_ext(30))
    assert res.decision == ApplicationStatus.AUTO_APPROVED

    # 29 days -> under buffer -> fail
    res = rules_engine.evaluate(app, get_ext(29))
    assert res.decision == ApplicationStatus.AUTO_REJECTED
    assert res.rejection_reason == "government_id_expired"

def test_extraction_failure_routing():
    app = Application(requested_loan_amount=5000, applicant_name="Test")
    
    # 1. Extraction has errors -> HUMAN_REVIEW
    ext = ApplicationExtractionResult(has_errors=True, errors=["Timeout"])
    res = rules_engine.evaluate(app, ext)
    assert res.decision == ApplicationStatus.HUMAN_REVIEW
    assert "extraction_failed" in res.flags
    
    # 2. Missing documents (no error flag) -> AUTO_REJECTED
    ext2 = ApplicationExtractionResult(has_errors=False)
    res2 = rules_engine.evaluate(app, ext2)
    assert res2.decision == ApplicationStatus.AUTO_REJECTED
    assert res2.rejection_reason == "missing_required_document_government_id"

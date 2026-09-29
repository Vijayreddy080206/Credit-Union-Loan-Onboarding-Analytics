import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from uuid import uuid4
import httpx
from datetime import date

from models.application import Application, ApplicationStatus, DocumentType
from schemas.extraction import ApplicationExtractionResult, DocumentExtractionResult
from services.rules_engine import rules_engine
from services.extraction.service import ExtractionService
from services.extraction.llm_adapter import GroqAdapter

@pytest.fixture
def mock_app():
    return Application(
        applicant_name="Test Applicant",
        applicant_email="test@example.com",
        requested_loan_amount=5000.0,
        loan_purpose="Test"
    )

def _get_failing_extraction_result(error_msg: str) -> ApplicationExtractionResult:
    return ApplicationExtractionResult(
        has_errors=True,
        errors=[error_msg]
    )

def test_extraction_timeout_leads_to_human_review(mock_app):
    extraction = _get_failing_extraction_result("LLM Extraction failed: Timeout")
    result = rules_engine.evaluate(mock_app, extraction)
    assert result.decision == ApplicationStatus.HUMAN_REVIEW
    assert "extraction_failed" in result.flags

def test_extraction_429_leads_to_human_review(mock_app):
    extraction = _get_failing_extraction_result("LLM Extraction failed: 429 Too Many Requests")
    result = rules_engine.evaluate(mock_app, extraction)
    assert result.decision == ApplicationStatus.HUMAN_REVIEW
    assert "extraction_failed" in result.flags

def test_extraction_invalid_json_leads_to_human_review(mock_app):
    extraction = _get_failing_extraction_result("LLM Extraction failed: Invalid JSON response")
    result = rules_engine.evaluate(mock_app, extraction)
    assert result.decision == ApplicationStatus.HUMAN_REVIEW
    assert "extraction_failed" in result.flags

def test_extraction_refusal_leads_to_human_review(mock_app):
    extraction = _get_failing_extraction_result("LLM Extraction failed: Model refused to answer")
    result = rules_engine.evaluate(mock_app, extraction)
    assert result.decision == ApplicationStatus.HUMAN_REVIEW
    assert "extraction_failed" in result.flags

def test_extraction_missing_api_key_leads_to_human_review(mock_app):
    extraction = _get_failing_extraction_result("LLM Extraction failed: Missing GROQ_API_KEY")
    result = rules_engine.evaluate(mock_app, extraction)
    assert result.decision == ApplicationStatus.HUMAN_REVIEW
    assert "extraction_failed" in result.flags

def test_genuinely_missing_document_leads_to_auto_reject(mock_app):
    from schemas.extraction import ProofOfIncomeExtraction, AddressProofExtraction
    
    # Missing document means government_id is None, not an object with an error
    extraction = ApplicationExtractionResult(
        government_id=None,
        proof_of_income=ProofOfIncomeExtraction(),
        address_proof=AddressProofExtraction(),
        has_errors=False,
    )
    result = rules_engine.evaluate(mock_app, extraction)
    assert result.decision == ApplicationStatus.AUTO_REJECTED
    assert result.rejection_reason == "missing_required_document_government_id"


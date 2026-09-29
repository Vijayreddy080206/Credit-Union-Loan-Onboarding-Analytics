"""
Rules Engine — Deterministic business logic.

The LLM extracts data. The Rules Engine makes decisions.
This separation is crucial for auditability and compliance.

We process rules in phases:
1. Hard Rejections (e.g. under 18, expired ID, low income)
2. Human-in-the-Loop Flags (e.g. low extraction confidence, name mismatch)
3. Auto-Approval (if no rejections and no flags)
"""
from datetime import date
import structlog
from models.application import Application, ApplicationStatus
from schemas.extraction import ApplicationExtractionResult
from schemas.rules import RuleResult, RulesEngineResult

logger = structlog.get_logger(__name__)

# Constants
MIN_AGE = 18
MAX_AGE = 70
MIN_MONTHLY_INCOME = 1500.0
MAX_LOAN_TO_INCOME_RATIO = 6.0
CONFIDENCE_THRESHOLD = 0.80

class RulesEngine:
    def evaluate(self, application: Application, extraction: ApplicationExtractionResult) -> RulesEngineResult:
        logger.info("rules_engine_evaluating", app_id=str(application.id))
        
        # 1. Missing Documents Check
        if not extraction.government_id:
            return RulesEngineResult(
                decision=ApplicationStatus.AUTO_REJECTED,
                rejection_reason="missing_required_document_government_id"
            )
        if not extraction.proof_of_income:
            return RulesEngineResult(
                decision=ApplicationStatus.AUTO_REJECTED,
                rejection_reason="missing_required_document_proof_of_income"
            )

        # 2. Hard Rejections
        
        # Expired ID
        if extraction.government_id.expiry_date.is_confident(CONFIDENCE_THRESHOLD):
            try:
                expiry = date.fromisoformat(extraction.government_id.expiry_date.value)
                if expiry < date.today():
                    return RulesEngineResult(
                        decision=ApplicationStatus.AUTO_REJECTED,
                        rejection_reason="government_id_expired"
                    )
            except (ValueError, TypeError):
                pass
                
        # Age constraints
        if extraction.government_id.date_of_birth.is_confident(CONFIDENCE_THRESHOLD):
            try:
                dob = date.fromisoformat(extraction.government_id.date_of_birth.value)
                age = (date.today() - dob).days / 365.25
                if age < MIN_AGE:
                    return RulesEngineResult(
                        decision=ApplicationStatus.AUTO_REJECTED,
                        rejection_reason="applicant_under_minimum_age"
                    )
                if age > MAX_AGE:
                    return RulesEngineResult(
                        decision=ApplicationStatus.AUTO_REJECTED,
                        rejection_reason="applicant_over_maximum_age"
                    )
            except (ValueError, TypeError):
                pass

        # Income constraints
        if extraction.proof_of_income.monthly_income.is_confident(CONFIDENCE_THRESHOLD):
            try:
                monthly_income = float(extraction.proof_of_income.monthly_income.value.replace(",", "").replace("$", ""))
                if monthly_income < MIN_MONTHLY_INCOME:
                    return RulesEngineResult(
                        decision=ApplicationStatus.AUTO_REJECTED,
                        rejection_reason="monthly_income_below_minimum"
                    )
                    
                # Loan-to-income ratio
                if application.requested_loan_amount:
                    annual_income = monthly_income * 12
                    ratio = float(application.requested_loan_amount) / annual_income
                    if ratio > MAX_LOAN_TO_INCOME_RATIO:
                        return RulesEngineResult(
                            decision=ApplicationStatus.AUTO_REJECTED,
                            rejection_reason="loan_exceeds_income_ratio"
                        )
            except (ValueError, TypeError):
                pass

        # 3. Human Review Flags
        flags = []
        
        # Low confidence extraction
        if extraction.overall_min_confidence < CONFIDENCE_THRESHOLD:
            flags.append("low_extraction_confidence")
            
        # Name mismatch
        if (extraction.government_id.full_name.is_confident(CONFIDENCE_THRESHOLD) and 
            application.applicant_name):
            name_on_id = extraction.government_id.full_name.value.lower().strip()
            name_on_app = application.applicant_name.lower().strip()
            # Simple check, real world would use fuzzy matching
            if name_on_id != name_on_app:
                flags.append("name_mismatch")

        if flags:
            return RulesEngineResult(
                decision=ApplicationStatus.HUMAN_REVIEW,
                flags=flags
            )

        # 4. Auto Approval
        return RulesEngineResult(decision=ApplicationStatus.AUTO_APPROVED)

rules_engine = RulesEngine()

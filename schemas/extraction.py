"""
Pydantic v2 schemas for LLM document extraction results.

Key principle: EVERY extracted field carries a confidence score (0–1).
The LLM returns both value and confidence. The rules engine ONLY trusts
fields with confidence >= threshold. This means:
- Blurry field -> low confidence -> HUMAN_REVIEW, not wrong auto-decision
- Field is present but LLM uncertain -> flag it, don't silently trust it

Why per-field confidence instead of per-document?
A document can have a clearly readable name but a smudged expiry date.
Per-field granularity lets the rules engine know exactly which piece of
data is uncertain — critical for fair lending compliance.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class FieldResult(BaseModel):
    """A single extracted field paired with its extraction confidence."""
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    def is_confident(self, threshold: float = 0.80) -> bool:
        return self.confidence >= threshold and self.value is not None


class GovernmentIDExtraction(BaseModel):
    """Structured output from reading a government-issued ID document."""
    full_name: FieldResult = Field(default_factory=lambda: FieldResult())
    date_of_birth: FieldResult = Field(default_factory=lambda: FieldResult())
    id_number: FieldResult = Field(default_factory=lambda: FieldResult())
    address: FieldResult = Field(default_factory=lambda: FieldResult())
    expiry_date: FieldResult = Field(default_factory=lambda: FieldResult())
    is_damaged: bool = False

    @property
    def min_confidence(self) -> float:
        return min(
            self.full_name.confidence,
            self.date_of_birth.confidence,
            self.id_number.confidence,
            self.expiry_date.confidence,
        )

    @property
    def key_fields(self) -> list[FieldResult]:
        return [self.full_name, self.date_of_birth, self.id_number, self.expiry_date]


class ProofOfIncomeExtraction(BaseModel):
    """Structured output from reading a proof-of-income document."""
    employee_name: FieldResult = Field(default_factory=lambda: FieldResult())
    employer: FieldResult = Field(default_factory=lambda: FieldResult())
    monthly_income: FieldResult = Field(default_factory=lambda: FieldResult())
    annual_income: FieldResult = Field(default_factory=lambda: FieldResult())
    pay_period: FieldResult = Field(default_factory=lambda: FieldResult())
    is_damaged: bool = False

    @property
    def min_confidence(self) -> float:
        return min(self.employee_name.confidence, self.monthly_income.confidence)

    @property
    def monthly_income_float(self) -> Optional[float]:
        if not self.monthly_income.value:
            return None
        try:
            return float(self.monthly_income.value.replace(",", "").replace("$", ""))
        except ValueError:
            return None


class AddressProofExtraction(BaseModel):
    """Structured output from reading an address proof document."""
    account_holder: FieldResult = Field(default_factory=lambda: FieldResult())
    service_address: FieldResult = Field(default_factory=lambda: FieldResult())
    utility_company: FieldResult = Field(default_factory=lambda: FieldResult())
    bill_date: FieldResult = Field(default_factory=lambda: FieldResult())
    is_damaged: bool = False

    @property
    def min_confidence(self) -> float:
        return min(self.account_holder.confidence, self.service_address.confidence)


class DocumentExtractionResult(BaseModel):
    """Full result for one document: parsed extraction + metadata."""
    document_type: str
    government_id: Optional[GovernmentIDExtraction] = None
    proof_of_income: Optional[ProofOfIncomeExtraction] = None
    address_proof: Optional[AddressProofExtraction] = None
    min_confidence: float = 0.0
    extraction_method: str = "mock"  # "mock" | "openai" | "anthropic"
    error: Optional[str] = None


class ApplicationExtractionResult(BaseModel):
    """Aggregated extraction across ALL documents for one application."""
    government_id: Optional[GovernmentIDExtraction] = None
    proof_of_income: Optional[ProofOfIncomeExtraction] = None
    address_proof: Optional[AddressProofExtraction] = None
    overall_min_confidence: float = 1.0
    extraction_method: str = "mock"
    has_errors: bool = False
    errors: list[str] = []

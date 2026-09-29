"""
LLM adapter interface + implementations (OpenAI, Anthropic, Mock).

This is the Adapter pattern in practice:
  BaseLLMAdapter defines the contract.
  Each concrete class implements it differently.
  The ExtractionService only talks to BaseLLMAdapter — it never knows
  which provider is being used.

Why a Mock adapter?
- Zero API cost in CI and local dev
- Deterministic output (same PDF = same extraction every run)
- Lets you run the full evaluation harness (Phase 8) without an API key
- The mock reads the PDF text directly and parses it with regex
  (works because our synthetic PDFs have structured, machine-readable text)

In a real system: the mock adapter runs in dev/test, real adapter in production.
Swap by changing LLM_PROVIDER= in .env. Zero code change.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from schemas.extraction import (
    AddressProofExtraction,
    FieldResult,
    GovernmentIDExtraction,
    ProofOfIncomeExtraction,
)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseLLMAdapter(ABC):
    """Every LLM adapter must implement this interface."""

    @abstractmethod
    async def extract_government_id(self, text: str) -> GovernmentIDExtraction:
        ...

    @abstractmethod
    async def extract_proof_of_income(self, text: str) -> ProofOfIncomeExtraction:
        ...

    @abstractmethod
    async def extract_address_proof(self, text: str) -> AddressProofExtraction:
        ...

    @property
    @abstractmethod
    def method_name(self) -> str:
        """Identifier written to audit log: 'mock', 'openai', 'anthropic'."""
        ...


# ---------------------------------------------------------------------------
# Mock adapter — regex-based, no API calls
# ---------------------------------------------------------------------------

def _r(text: str, pattern: str, confidence_clean: float = 0.95,
        confidence_damaged: float = 0.55) -> FieldResult:
    """
    Try to match `pattern` in `text`. Return a FieldResult with confidence:
    - High confidence if match found AND document is not marked DAMAGED
    - Low confidence if document is DAMAGED (simulates blurry/unclear scan)
    - Zero confidence if field not found
    """
    is_damaged = "DAMAGED" in text
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        value = match.group(1).strip()
        conf = confidence_damaged if is_damaged else confidence_clean
        return FieldResult(value=value, confidence=conf)
    return FieldResult(value=None, confidence=0.0)


class MockLLMAdapter(BaseLLMAdapter):
    """
    Parses our synthetic PDF text with regex patterns.
    Returns high confidence for clean docs, low for DAMAGED watermarked docs.
    This is what runs in CI, local dev, and the evaluation harness by default.
    """

    @property
    def method_name(self) -> str:
        return "mock"

    async def extract_government_id(self, text: str) -> GovernmentIDExtraction:
        is_damaged = "DAMAGED" in text
        return GovernmentIDExtraction(
            full_name=_r(text, r"Full Name:\s*(.+)"),
            date_of_birth=_r(text, r"Date of Birth:\s*(.+)"),
            id_number=_r(text, r"ID Number:\s*(.+)"),
            address=_r(text, r"Address:\s*(.+)"),
            expiry_date=_r(text, r"Expiry Date:\s*(.+)"),
            is_damaged=is_damaged,
        )

    async def extract_proof_of_income(self, text: str) -> ProofOfIncomeExtraction:
        is_damaged = "DAMAGED" in text
        monthly = _r(text, r"Monthly Income:\s*\$?([\d,]+\.?\d*)")
        annual = _r(text, r"Annual Income:\s*\$?([\d,]+\.?\d*)")
        return ProofOfIncomeExtraction(
            employee_name=_r(text, r"Employee Name:\s*(.+)"),
            employer=_r(text, r"Employer:\s*(.+)"),
            monthly_income=monthly,
            annual_income=annual,
            pay_period=_r(text, r"Pay Period:\s*(.+)"),
            is_damaged=is_damaged,
        )

    async def extract_address_proof(self, text: str) -> AddressProofExtraction:
        is_damaged = "DAMAGED" in text
        return AddressProofExtraction(
            account_holder=_r(text, r"Account Holder:\s*(.+)"),
            service_address=_r(text, r"Service Address:\s*(.+)"),
            utility_company=_r(text, r"Utility Company:\s*(.+)"),
            bill_date=_r(text, r"Bill Date:\s*(.+)"),
            is_damaged=is_damaged,
        )


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

OPENAI_SYSTEM_PROMPT = """You are a KYC document extraction assistant for a credit union.
Extract information from the document text provided and return ONLY valid JSON.
For each field, provide a "value" (string or null) and a "confidence" (float 0.0-1.0).
Set confidence = 0.0 if the field is missing or illegible.
Set confidence >= 0.9 if the field is clearly readable.
Set confidence 0.5-0.8 if the field is partially legible or uncertain.
ALL DATA IS SYNTHETIC. This is a test system. Extract exactly what you see."""

OPENAI_ID_PROMPT = """Extract from this government ID document:
{text}

Return JSON with this exact structure:
{{
  "full_name": {{"value": "...", "confidence": 0.0}},
  "date_of_birth": {{"value": "YYYY-MM-DD or null", "confidence": 0.0}},
  "id_number": {{"value": "...", "confidence": 0.0}},
  "address": {{"value": "...", "confidence": 0.0}},
  "expiry_date": {{"value": "YYYY-MM-DD or null", "confidence": 0.0}},
  "is_damaged": false
}}"""

OPENAI_INCOME_PROMPT = """Extract from this proof of income document:
{text}

Return JSON with this exact structure:
{{
  "employee_name": {{"value": "...", "confidence": 0.0}},
  "employer": {{"value": "...", "confidence": 0.0}},
  "monthly_income": {{"value": "numeric amount only e.g. 3500.00", "confidence": 0.0}},
  "annual_income": {{"value": "numeric amount only", "confidence": 0.0}},
  "pay_period": {{"value": "...", "confidence": 0.0}},
  "is_damaged": false
}}"""

OPENAI_ADDRESS_PROMPT = """Extract from this address proof document:
{text}

Return JSON with this exact structure:
{{
  "account_holder": {{"value": "...", "confidence": 0.0}},
  "service_address": {{"value": "...", "confidence": 0.0}},
  "utility_company": {{"value": "...", "confidence": 0.0}},
  "bill_date": {{"value": "YYYY-MM-DD or null", "confidence": 0.0}},
  "is_damaged": false
}}"""


class OpenAIAdapter(BaseLLMAdapter):
    """Calls OpenAI API with JSON mode for structured extraction."""

    def __init__(self, api_key: str, model: str, timeout: int = 30, max_retries: int = 3):
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)
            self._model = model
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

    @property
    def method_name(self) -> str:
        return "openai"

    async def _call(self, user_prompt: str) -> dict[str, Any]:
        import json
        response = await self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": OPENAI_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return json.loads(response.choices[0].message.content)

    async def extract_government_id(self, text: str) -> GovernmentIDExtraction:
        data = await self._call(OPENAI_ID_PROMPT.format(text=text[:3000]))
        return GovernmentIDExtraction(**data)

    async def extract_proof_of_income(self, text: str) -> ProofOfIncomeExtraction:
        data = await self._call(OPENAI_INCOME_PROMPT.format(text=text[:3000]))
        return ProofOfIncomeExtraction(**data)

    async def extract_address_proof(self, text: str) -> AddressProofExtraction:
        data = await self._call(OPENAI_ADDRESS_PROMPT.format(text=text[:3000]))
        return AddressProofExtraction(**data)


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

class AnthropicAdapter(BaseLLMAdapter):
    """Calls Anthropic Claude API for structured extraction."""

    def __init__(self, api_key: str, model: str, timeout: int = 30, max_retries: int = 3):
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            self._model = model
            self._timeout = timeout
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

    @property
    def method_name(self) -> str:
        return "anthropic"

    async def _call(self, user_prompt: str) -> dict[str, Any]:
        import json
        msg = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=OPENAI_SYSTEM_PROMPT + "\nReturn ONLY the JSON object, no explanation.",
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = msg.content[0].text.strip()
        # Claude sometimes wraps JSON in ```json ... ```
        if text.startswith("```"):
            text = re.sub(r"^```json?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)

    async def extract_government_id(self, text: str) -> GovernmentIDExtraction:
        data = await self._call(OPENAI_ID_PROMPT.format(text=text[:3000]))
        return GovernmentIDExtraction(**data)

    async def extract_proof_of_income(self, text: str) -> ProofOfIncomeExtraction:
        data = await self._call(OPENAI_INCOME_PROMPT.format(text=text[:3000]))
        return ProofOfIncomeExtraction(**data)

    async def extract_address_proof(self, text: str) -> AddressProofExtraction:
        data = await self._call(OPENAI_ADDRESS_PROMPT.format(text=text[:3000]))
        return AddressProofExtraction(**data)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_llm_adapter(provider: str, **kwargs) -> BaseLLMAdapter:
    """
    Factory: returns the right adapter based on LLM_PROVIDER env var.
    Called once at startup by the ExtractionService.
    """
    if provider == "mock":
        return MockLLMAdapter()
    elif provider == "openai":
        return OpenAIAdapter(**kwargs)
    elif provider == "anthropic":
        return AnthropicAdapter(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}. Choose: mock | openai | anthropic")

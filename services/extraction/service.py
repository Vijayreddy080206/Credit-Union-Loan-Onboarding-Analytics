"""
Main Extraction Service.

Orchestrates reading a PDF, calling the LLM adapter, and returning structured data.
This is called by the API layer or the n8n webhook when documents are uploaded.
"""
from typing import Optional

import structlog

from core.config import settings
from models.application import DocumentType
from schemas.extraction import (
    AddressProofExtraction,
    DocumentExtractionResult,
    GovernmentIDExtraction,
    ProofOfIncomeExtraction,
)
from services.extraction.llm_adapter import get_llm_adapter
from services.extraction.pdf_reader import extract_text_from_bytes, extract_text_from_pdf

logger = structlog.get_logger(__name__)


class ExtractionService:
    def __init__(self):
        # Instantiate the correct LLM adapter based on env settings
        kwargs = {}
        if settings.LLM_PROVIDER == "openai":
            kwargs = {"api_key": settings.OPENAI_API_KEY, "model": settings.OPENAI_MODEL}
        elif settings.LLM_PROVIDER == "anthropic":
            kwargs = {"api_key": settings.ANTHROPIC_API_KEY, "model": settings.ANTHROPIC_MODEL}
        
        self.llm = get_llm_adapter(settings.LLM_PROVIDER, **kwargs)

    async def extract_document(
        self, doc_type: DocumentType, file_path: Optional[str] = None, file_bytes: Optional[bytes] = None
    ) -> DocumentExtractionResult:
        """
        Extracts structured data from a PDF document.
        Can accept either a file path or raw bytes.
        """
        logger.info("extracting_document", doc_type=doc_type.value, provider=self.llm.method_name)

        if file_path:
            text = extract_text_from_pdf(file_path)
        elif file_bytes:
            text = extract_text_from_bytes(file_bytes)
        else:
            return DocumentExtractionResult(
                document_type=doc_type.value,
                error="No file path or bytes provided."
            )

        if not text or text.startswith("PDF_READ_ERROR"):
            logger.error("pdf_read_failed", doc_type=doc_type.value, error=text)
            return DocumentExtractionResult(
                document_type=doc_type.value,
                error=text or "Failed to extract text from PDF."
            )

        try:
            if doc_type == DocumentType.GOVERNMENT_ID:
                result = await self.llm.extract_government_id(text)
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    government_id=result,
                    min_confidence=result.min_confidence,
                    extraction_method=self.llm.method_name
                )
            elif doc_type == DocumentType.PROOF_OF_INCOME:
                result = await self.llm.extract_proof_of_income(text)
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    proof_of_income=result,
                    min_confidence=result.min_confidence,
                    extraction_method=self.llm.method_name
                )
            elif doc_type == DocumentType.ADDRESS_PROOF:
                result = await self.llm.extract_address_proof(text)
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    address_proof=result,
                    min_confidence=result.min_confidence,
                    extraction_method=self.llm.method_name
                )
            else:
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    error=f"Unsupported document type: {doc_type.value}"
                )
        except Exception as e:
            logger.exception("llm_extraction_failed", doc_type=doc_type.value, exc=str(e))
            return DocumentExtractionResult(
                document_type=doc_type.value,
                error=f"LLM Extraction failed: {str(e)}"
            )

# Singleton instance
extraction_service = ExtractionService()

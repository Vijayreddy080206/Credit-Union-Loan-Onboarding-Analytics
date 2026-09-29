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
from services.extraction.pdf_reader import extract_text_from_bytes, extract_text_from_pdf, render_pdf_to_image_base64

logger = structlog.get_logger(__name__)


class ExtractionService:
    def __init__(self):
        # Instantiate the correct LLM adapter based on env settings
        kwargs = {}
        if settings.LLM_PROVIDER == "openai":
            kwargs = {"api_key": settings.OPENAI_API_KEY, "model": settings.OPENAI_MODEL}
        elif settings.LLM_PROVIDER == "anthropic":
            kwargs = {"api_key": settings.ANTHROPIC_API_KEY, "model": settings.ANTHROPIC_MODEL}
        elif settings.LLM_PROVIDER == "groq":
            kwargs = {
                "api_key": settings.GROQ_API_KEY,
                "base_url": settings.GROQ_BASE_URL,
                "text_model": settings.GROQ_TEXT_MODEL,
                "vision_model": settings.GROQ_VISION_MODEL,
            }
        
        self.llm = get_llm_adapter(settings.LLM_PROVIDER, **kwargs)

    async def extract_document(
        self, doc_type: DocumentType, file_path: Optional[str] = None, file_bytes: Optional[bytes] = None
    ) -> DocumentExtractionResult:
        """
        Extracts structured data from a PDF document.
        Can accept either a file path or raw bytes.
        """
        logger.info("extracting_document", doc_type=doc_type.value, provider=self.llm.method_name)

        if file_path and not file_bytes:
            try:
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
            except Exception as exc:
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    error=f"Failed to read file: {exc}"
                )
                
        if not file_bytes:
            return DocumentExtractionResult(
                document_type=doc_type.value,
                error="No file bytes provided."
            )

        text = extract_text_from_bytes(file_bytes)
        
        # Vision fallback if text is very short (e.g. scanned image PDF)
        is_vision = False
        image_base64 = None
        if len(text.strip()) < 50:
            is_vision = True
            image_base64 = render_pdf_to_image_base64(file_bytes)
            if not image_base64:
                # Could not render
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    error="Failed to extract text or render image."
                )

        try:
            if doc_type == DocumentType.GOVERNMENT_ID:
                result = await self.llm.extract_government_id(text, is_vision, image_base64)
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    government_id=result,
                    min_confidence=result.min_confidence,
                    extraction_method=self.llm.method_name + ("_vision" if is_vision else "_text")
                )
            elif doc_type == DocumentType.PROOF_OF_INCOME:
                result = await self.llm.extract_proof_of_income(text, is_vision, image_base64)
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    proof_of_income=result,
                    min_confidence=result.min_confidence,
                    extraction_method=self.llm.method_name + ("_vision" if is_vision else "_text")
                )
            elif doc_type == DocumentType.ADDRESS_PROOF:
                result = await self.llm.extract_address_proof(text, is_vision, image_base64)
                return DocumentExtractionResult(
                    document_type=doc_type.value,
                    address_proof=result,
                    min_confidence=result.min_confidence,
                    extraction_method=self.llm.method_name + ("_vision" if is_vision else "_text")
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

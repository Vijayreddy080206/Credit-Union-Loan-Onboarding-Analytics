"""
Pydantic schemas for the REST API (Phase 5).
"""
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from models.application import ApplicationStatus, DocumentType

class ApplicationCreate(BaseModel):
    idempotency_key: str
    applicant_name: str
    applicant_email: str
    requested_loan_amount: float
    loan_purpose: Optional[str] = None

class ApplicationResponse(BaseModel):
    id: UUID
    applicant_name: str
    applicant_email: str
    requested_loan_amount: float
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class DocumentUploadResponse(BaseModel):
    id: UUID
    application_id: UUID
    document_type: DocumentType
    file_path: str
    
    model_config = ConfigDict(from_attributes=True)

class ReviewSubmit(BaseModel):
    decision: str  # "APPROVED" or "REJECTED"
    override_reason: Optional[str] = None
    reviewer_id: str

class AuditLogResponse(BaseModel):
    id: UUID
    event_type: str
    event_data: dict
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

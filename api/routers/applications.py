"""Application submission and status endpoints."""
import os
import shutil
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from models.application import Application, ApplicationDocument, DocumentType, ApplicationStatus
from schemas.api import ApplicationCreate, ApplicationResponse, DocumentUploadResponse
from services.audit import write_event
from models.audit_log import AuditEventType

router = APIRouter()

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/", response_model=ApplicationResponse)
async def create_application(app_data: ApplicationCreate, db: AsyncSession = Depends(get_db)):
    """Create a new loan application."""
    # Idempotency check
    result = await db.execute(select(Application).where(Application.idempotency_key == app_data.idempotency_key))
    existing_app = result.scalar_one_or_none()
    if existing_app:
        return existing_app
        
    new_app = Application(
        idempotency_key=app_data.idempotency_key,
        applicant_name=app_data.applicant_name,
        applicant_email=app_data.applicant_email,
        requested_loan_amount=app_data.requested_loan_amount,
        loan_purpose=app_data.loan_purpose,
        status=ApplicationStatus.SUBMITTED
    )
    db.add(new_app)
    await db.flush()  # to get the ID
    
    await write_event(db, new_app.id, AuditEventType.APPLICATION_SUBMITTED, "system", "Application submitted", details=app_data.model_dump())
    
    await db.commit()
    await db.refresh(new_app)
    return new_app

@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get status of an application."""
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app

@router.post("/{app_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    app_id: UUID, 
    doc_type: DocumentType, 
    file: UploadFile = File(...), 
    db: AsyncSession = Depends(get_db)
):
    """Upload a document for an application."""
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    file_path = os.path.join(UPLOAD_DIR, f"{app_id}_{doc_type.value}.pdf")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    doc = ApplicationDocument(
        application_id=app_id,
        document_type=doc_type,
        file_path=file_path
    )
    db.add(doc)
    
    await write_event(db, app_id, AuditEventType.DOCUMENT_UPLOADED, "system", f"Document {doc_type.value} uploaded", details={"file_path": file_path})
    
    await db.commit()
    await db.refresh(doc)
    return doc

@router.post("/{app_id}/process")
async def trigger_processing(app_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Trigger the pipeline (Extraction -> Rules).
    Normally this is done by an orchestrator like n8n, but having an endpoint is useful.
    """
    from services.extraction.service import extraction_service
    from services.rules_engine import rules_engine
    from schemas.extraction import ApplicationExtractionResult
    
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    docs_result = await db.execute(select(ApplicationDocument).where(ApplicationDocument.application_id == app_id))
    docs = docs_result.scalars().all()
    
    extracted_data = ApplicationExtractionResult()
    for doc in docs:
        ext_res = await extraction_service.extract_document(doc.document_type, file_path=doc.file_path)
        if ext_res.error:
            extracted_data.has_errors = True
            extracted_data.errors.append(ext_res.error)
        else:
            if doc.document_type == DocumentType.GOVERNMENT_ID:
                extracted_data.government_id = ext_res.government_id
            elif doc.document_type == DocumentType.PROOF_OF_INCOME:
                extracted_data.proof_of_income = ext_res.proof_of_income
            elif doc.document_type == DocumentType.ADDRESS_PROOF:
                extracted_data.address_proof = ext_res.address_proof
            extracted_data.overall_min_confidence = min(extracted_data.overall_min_confidence, ext_res.min_confidence)
            
    app.extraction_result = extracted_data.model_dump()
    await write_event(db, app_id, AuditEventType.EXTRACTION_COMPLETED, "system", "Extraction completed", details=app.extraction_result)
    
    rules_res = rules_engine.evaluate(app, extracted_data)
    app.status = rules_res.decision
    app.rejection_reason = rules_res.rejection_reason
    app.flags = rules_res.flags
    
    await write_event(db, app_id, AuditEventType.RULES_EVALUATED, "system", "Rules evaluated", details=rules_res.model_dump())
    
    if app.status == ApplicationStatus.AUTO_APPROVED:
        await write_event(db, app_id, AuditEventType.AUTO_APPROVED, "system", "Auto approved", details=rules_res.model_dump())
    elif app.status == ApplicationStatus.AUTO_REJECTED:
        await write_event(db, app_id, AuditEventType.AUTO_REJECTED, "system", "Auto rejected", details=rules_res.model_dump())
    elif app.status == ApplicationStatus.HUMAN_REVIEW:
        await write_event(db, app_id, AuditEventType.ROUTED_TO_HUMAN, "system", "Routed to human review", details=rules_res.model_dump())
        
    # CRM Sync
    from services.crm import crm_service
    try:
        await crm_service.sync_application(app_id, app.applicant_name, app.applicant_email, app.status.value)
    except Exception as e:
        # DB transaction is rolled back on exception in fastapi dependency if we raise,
        # but since we already caught it we must rollback manually if we don't raise immediately.
        # Actually, since we use AsyncSession, if we raise HTTPException, FastAPI's session dependency
        # might just rollback depending on how it's written. Let's manually rollback to be safe.
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"CRM Sync Failed: {str(e)}")
        
    await db.commit()
    
    return {"message": "Processed", "decision": app.status.value, "flags": app.flags}

from pydantic import BaseModel

class ReviewRequest(BaseModel):
    reviewer_id: str
    notes: str = ""

@router.post("/{app_id}/approve")
async def approve_application(app_id: UUID, req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    """Human manually approves an application."""
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app.status != ApplicationStatus.HUMAN_REVIEW:
        raise HTTPException(status_code=400, detail=f"Cannot approve app in status {app.status}")
        
    app.status = ApplicationStatus.MANUALLY_APPROVED
    await write_event(db, app_id, AuditEventType.MANUALLY_APPROVED, req.reviewer_id, "Manually approved", details=req.model_dump())
    await db.commit()
    return {"message": "Approved"}

@router.post("/{app_id}/reject")
async def reject_application(app_id: UUID, req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    """Human manually rejects an application."""
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app.status != ApplicationStatus.HUMAN_REVIEW:
        raise HTTPException(status_code=400, detail=f"Cannot reject app in status {app.status}")
        
    app.status = ApplicationStatus.MANUALLY_REJECTED
    app.rejection_reason = "manual_review_rejection"
    await write_event(db, app_id, AuditEventType.MANUALLY_REJECTED, req.reviewer_id, "Manually rejected", details=req.model_dump())
    await db.commit()
    return {"message": "Rejected"}

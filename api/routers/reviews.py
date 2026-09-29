"""Reviewer approve/reject endpoints for Human-in-the-Loop."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from models.application import Application, ApplicationStatus
from models.reviewer import ReviewDecision
from schemas.api import ReviewSubmit
from services.audit import write_event
from models.audit_log import AuditEventType

router = APIRouter()

@router.post("/{app_id}/review")
async def submit_review(app_id: UUID, review_data: ReviewSubmit, db: AsyncSession = Depends(get_db)):
    """Submit a human review decision."""
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app.status != ApplicationStatus.HUMAN_REVIEW:
        raise HTTPException(status_code=400, detail=f"Application is in {app.status} state, not HUMAN_REVIEW")
        
    if review_data.decision not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Decision must be APPROVED or REJECTED")
        
    new_status = ApplicationStatus.APPROVED if review_data.decision == "APPROVED" else ApplicationStatus.REJECTED
    
    # Save the review record
    review = ReviewDecision(
        application_id=app_id,
        reviewer_id=review_data.reviewer_id,
        decision=review_data.decision,
        override_reason=review_data.override_reason
    )
    db.add(review)
    
    # Update app status
    app.status = new_status
    
    # Audit log
    event_type = AuditEventType.MANUALLY_APPROVED if new_status == ApplicationStatus.APPROVED else AuditEventType.MANUALLY_REJECTED
    await write_event(db, app_id, event_type, review_data.model_dump())
    
    await db.commit()
    return {"message": "Review submitted successfully", "new_status": new_status.value}

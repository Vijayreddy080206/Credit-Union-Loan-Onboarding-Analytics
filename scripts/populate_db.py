import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from core.database import AsyncSessionLocal
from models.application import Application, ApplicationDocument, DocumentType, ApplicationStatus
from schemas.extraction import ApplicationExtractionResult
from services.extraction.service import extraction_service
from services.rules_engine import rules_engine
from services.audit import write_event
from models.audit_log import AuditEventType

DATA_DIR = Path("data/synthetic")
APPLICANTS_FILE = DATA_DIR / "applicants.json"

async def populate():
    if not APPLICANTS_FILE.exists():
        print("Run generate.py first.")
        return

    with open(APPLICANTS_FILE, "r") as f:
        applicants = json.load(f)

    async with AsyncSessionLocal() as db:
        for app_data in applicants:
            app_id = UUID(app_data["application_id"])
            
            new_app = Application(
                id=app_id,
                applicant_name=app_data["applicant_name"],
                applicant_email=app_data["applicant_email"],
                requested_loan_amount=app_data["requested_loan_amount"],
                status=ApplicationStatus.SUBMITTED,
                idempotency_key=str(app_id)
            )
            db.add(new_app)
            await db.flush()
            
            ext_result = ApplicationExtractionResult()
            
            for doc in app_data.get("documents", []):
                doc_type = DocumentType(doc["type"])
                doc_path = f"/app/data/synthetic/docs/{app_id}/{doc_type.value.lower()}.pdf"
                
                db_doc = ApplicationDocument(
                    application_id=app_id,
                    document_type=doc_type,
                    file_path=doc_path
                )
                db.add(db_doc)
                
                res = await extraction_service.extract_document(doc_type, file_path=doc_path)
                if doc_type == DocumentType.GOVERNMENT_ID:
                    ext_result.government_id = res.government_id
                elif doc_type == DocumentType.PROOF_OF_INCOME:
                    ext_result.proof_of_income = res.proof_of_income
                elif doc_type == DocumentType.ADDRESS_PROOF:
                    ext_result.address_proof = res.address_proof
                    
                ext_result.overall_min_confidence = min(ext_result.overall_min_confidence, res.min_confidence)
                
            rules_res = rules_engine.evaluate(new_app, ext_result)
            new_app.status = rules_res.decision
            new_app.decision_reason = rules_res.rejection_reason
            new_app.extraction_result = ext_result.model_dump()
            new_app.rules_result = rules_res.model_dump()
            
            await write_event(db, app_id, AuditEventType.APPLICATION_SUBMITTED, actor="System", message="Submitted", details={"info": "submitted"})
            
            if new_app.status == ApplicationStatus.AUTO_APPROVED:
                await write_event(db, app_id, AuditEventType.RULES_CHECK_COMPLETED, actor="System", message="Approved", details={"decision": "AUTO_APPROVED"})
            elif new_app.status == ApplicationStatus.AUTO_REJECTED:
                await write_event(db, app_id, AuditEventType.RULES_CHECK_COMPLETED, actor="System", message="Rejected", details={"decision": "AUTO_REJECTED"})
            elif new_app.status == ApplicationStatus.HUMAN_REVIEW:
                await write_event(db, app_id, AuditEventType.RULES_CHECK_COMPLETED, actor="System", message="Human review", details={"decision": "HUMAN_REVIEW"})
                
        await db.commit()
    print("Database populated successfully!")

if __name__ == "__main__":
    asyncio.run(populate())

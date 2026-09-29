"""
Evaluation Harness (Phase 8).

This script reads the synthetic ground-truth data, runs the mock extraction 
and rules engine, and computes exactly how well the system performs.
This is the core "proof" of the project that you show in interviews.
"""
import asyncio
import json
import os
from pathlib import Path

from models.application import Application, DocumentType
from schemas.extraction import ApplicationExtractionResult
from services.extraction.service import extraction_service
from services.rules_engine import rules_engine

DATA_DIR = Path("data/synthetic")
APPLICANTS_FILE = DATA_DIR / "applicants.json"

async def evaluate_all():
    if not APPLICANTS_FILE.exists():
        print(f"File not found: {APPLICANTS_FILE}")
        print("Please run 'python data/synthetic/generate.py' first.")
        return

    with open(APPLICANTS_FILE, "r") as f:
        applicants = json.load(f)

    print(f"Starting evaluation of {len(applicants)} applications...")
    
    correct_decisions = 0
    confusion_matrix = {
        "AUTO_APPROVED": {"AUTO_APPROVED": 0, "AUTO_REJECTED": 0, "HUMAN_REVIEW": 0},
        "AUTO_REJECTED": {"AUTO_APPROVED": 0, "AUTO_REJECTED": 0, "HUMAN_REVIEW": 0},
        "HUMAN_REVIEW": {"AUTO_APPROVED": 0, "AUTO_REJECTED": 0, "HUMAN_REVIEW": 0},
    }

    for app_data in applicants:
        app_id = app_data["application_id"]
        
        # 1. Setup Mock Application
        app = Application(
            id=app_id,
            applicant_name=app_data["applicant_name"],
            applicant_email=app_data["applicant_email"],
            requested_loan_amount=app_data["requested_loan_amount"]
        )
        
        # 2. Extract Data
        ext_result = ApplicationExtractionResult()
        for doc in app_data.get("documents", []):
            doc_type = DocumentType(doc["type"])
            doc_path = doc["path"]
            
            res = await extraction_service.extract_document(doc_type, file_path=doc_path)
            
            if doc_type == DocumentType.GOVERNMENT_ID:
                ext_result.government_id = res.government_id
            elif doc_type == DocumentType.PROOF_OF_INCOME:
                ext_result.proof_of_income = res.proof_of_income
            elif doc_type == DocumentType.ADDRESS_PROOF:
                ext_result.address_proof = res.address_proof
                
            ext_result.overall_min_confidence = min(ext_result.overall_min_confidence, res.min_confidence)
            
        # 3. Run Rules Engine
        rules_res = rules_engine.evaluate(app, ext_result)
        
        expected = app_data["expected_decision"]
        actual = rules_res.decision.value
        
        confusion_matrix[expected][actual] += 1
        if expected == actual:
            correct_decisions += 1
        else:
            print(f"Mismatch [{app_data['scenario']}]: Expected {expected}, got {actual}")
            print(f"  Reason: {rules_res.rejection_reason}, Flags: {rules_res.flags}")

    # Print Metrics
    accuracy = (correct_decisions / len(applicants)) * 100
    print("\n" + "="*50)
    print("EVALUATION RESULTS")
    print("="*50)
    print(f"Total Applications: {len(applicants)}")
    print(f"Overall Accuracy:   {accuracy:.1f}%")
    
    print("\nConfusion Matrix (Rows: Expected, Cols: Actual):")
    print(f"{'':<15} | {'AUTO_APPROVED':<15} | {'AUTO_REJECTED':<15} | {'HUMAN_REVIEW':<15}")
    print("-" * 65)
    for expected in ["AUTO_APPROVED", "AUTO_REJECTED", "HUMAN_REVIEW"]:
        row = confusion_matrix[expected]
        print(f"{expected:<15} | {row['AUTO_APPROVED']:<15} | {row['AUTO_REJECTED']:<15} | {row['HUMAN_REVIEW']:<15}")

if __name__ == "__main__":
    # Ensure working dir is correct (project root)
    if not os.path.exists("data"):
        print("Please run this script from the project root directory.")
        exit(1)
        
    asyncio.run(evaluate_all())

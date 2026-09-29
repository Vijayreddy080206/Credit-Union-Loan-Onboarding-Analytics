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
    
    total_fields = 0
    correct_fields = 0
    field_errors = []

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
                actual_data = res.government_id.model_dump() if res.government_id else {}
            elif doc_type == DocumentType.PROOF_OF_INCOME:
                ext_result.proof_of_income = res.proof_of_income
                actual_data = res.proof_of_income.model_dump() if res.proof_of_income else {}
            elif doc_type == DocumentType.ADDRESS_PROOF:
                ext_result.address_proof = res.address_proof
                actual_data = res.address_proof.model_dump() if res.address_proof else {}
                
            ext_result.overall_min_confidence = min(ext_result.overall_min_confidence, res.min_confidence)
            
            # Compare with Ground Truth
            gt_path = Path(doc_path).parent / "ground_truth.json"
            if gt_path.exists():
                with open(gt_path, "r") as f:
                    gt = json.load(f)
                
                # Check fields
                # Not all ground truth fields apply to every document type, but we can do a naive intersection
                for k, v in gt.items():
                    if k in actual_data:
                        actual_val = actual_data[k].get("value") if isinstance(actual_data[k], dict) else actual_data[k]
                        total_fields += 1
                        
                        # Fuzzy match for numbers/dates (simple string containment for now)
                        if str(v).lower() in str(actual_val).lower() or str(actual_val).lower() in str(v).lower():
                            correct_fields += 1
                        else:
                            field_errors.append(f"{app_id[:8]} - {doc_type.value}.{k}: expected '{v}', got '{actual_val}'")
            
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
    field_accuracy = (correct_fields / total_fields) * 100 if total_fields > 0 else 0
    print("\n" + "="*50)
    print("EVALUATION RESULTS")
    print("="*50)
    print(f"Total Applications: {len(applicants)}")
    print(f"Overall Decision Accuracy:   {accuracy:.1f}%")
    print(f"Field Extraction Accuracy:   {field_accuracy:.1f}% ({correct_fields}/{total_fields})")
    
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

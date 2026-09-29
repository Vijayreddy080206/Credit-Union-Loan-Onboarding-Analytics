import asyncio
import json
import os
from pathlib import Path
import sys

from core.config import settings
from models.application import DocumentType
from services.extraction.service import extraction_service

DATA_DIR = Path("data/synthetic")
APPLICANTS_FILE = DATA_DIR / "applicants.json"

async def main():
    if not APPLICANTS_FILE.exists():
        print(f"File not found: {APPLICANTS_FILE}")
        return

    with open(APPLICANTS_FILE, "r") as f:
        applicants = json.load(f)

    # 5 text (CLEAN) and 5 vision (LOW_CONFIDENCE or ROTATED_DOCS)
    docs = []
    text_count = 0
    vision_count = 0
    
    for app in applicants:
        scenario = app.get("scenario")
        
        is_vision = scenario in ["LOW_CONFIDENCE", "ROTATED_DOCS"]
        if is_vision and vision_count >= 5:
            continue
        if not is_vision and text_count >= 5:
            continue
            
        for doc in app.get("documents", []):
            docs.append({
                "app_id": app["application_id"],
                "doc_type": doc["type"],
                "path": doc["path"],
                "expected": app.get("ground_truth", {})
            })
            if is_vision:
                vision_count += 1
            else:
                text_count += 1
            break # Just take one doc per app
            
        if text_count >= 5 and vision_count >= 5:
            break

    print(f"## Phase B Evidence: Real Groq Provider ({settings.GROQ_TEXT_MODEL}, {settings.GROQ_VISION_MODEL})")
    print(f"**Command executed:** `$env:PYTHONPATH=\".\"; python scripts/phase_b_evidence.py`\n")
    
    stats = {"text": {"matched": 0, "total": 0}, "vision": {"matched": 0, "total": 0}}
    
    for i, doc in enumerate(docs):
        print(f"### Document {i+1}: {doc['doc_type']} (App ID: {doc['app_id'][:8]})")
        print(f"- **Path**: `{doc['path']}`")
        
        doc_type = DocumentType(doc["doc_type"])
        res = await extraction_service.extract_document(doc_type, file_path=doc['path'])
        
        is_vision_path = "vision" in res.extraction_method
        path_type = "vision" if is_vision_path else "text"
        
        print(f"- **Extraction Method**: `{res.extraction_method}` (Vision Path Used: {'Yes' if is_vision_path else 'No'})")
        
        if res.error:
            print(f"- **Error**: {res.error}")
            continue

        actual_data = {}
        if doc_type == DocumentType.GOVERNMENT_ID and res.government_id:
            actual_data = res.government_id.model_dump()
        elif doc_type == DocumentType.PROOF_OF_INCOME and res.proof_of_income:
            actual_data = res.proof_of_income.model_dump()
        elif doc_type == DocumentType.ADDRESS_PROOF and res.address_proof:
            actual_data = res.address_proof.model_dump()
            
        print("\n| Field | Expected Value | Actual Value | Match | Confidence |")
        print("|-------|----------------|--------------|-------|------------|")
        
        expected = doc['expected']
        
        # Map fields to what the specific document expects to extract
        fields_to_check = []
        if doc_type == DocumentType.GOVERNMENT_ID:
            fields_to_check = [("name", "full_name", "name_on_id"), ("dob", "date_of_birth", "dob"), ("id_number", "id_number", "id_number"), ("address", "address", "address"), ("id_expiry", "expiry_date", "id_expiry")]
        elif doc_type == DocumentType.PROOF_OF_INCOME:
            fields_to_check = [("name", "employee_name", "name_on_form"), ("monthly_income", "monthly_income", "monthly_income"), ("employer", "employer", "employer")]
        elif doc_type == DocumentType.ADDRESS_PROOF:
            fields_to_check = [("name", "account_holder", "name_on_form"), ("address", "service_address", "address")]
            
        for gt_key, ext_key, fallback_gt_key in fields_to_check:
            # handle NAME_MISMATCH special case
            expected_val = expected.get(gt_key)
            if expected_val is None:
                expected_val = expected.get(fallback_gt_key)
                
            actual_val_obj = actual_data.get(ext_key, {})
            if isinstance(actual_val_obj, dict):
                actual_val = actual_val_obj.get("value")
                conf = actual_val_obj.get("confidence", 0.0)
            else:
                actual_val = actual_val_obj
                conf = 0.0
                
            # Formatting to string for comparison (like dates, floats)
            expected_str = str(expected_val).lower().strip() if expected_val is not None else "none"
            actual_str = str(actual_val).lower().strip() if actual_val is not None else "none"
            
            # Simple soft match for names, addresses
            match = "No"
            if expected_str == actual_str:
                match = "Yes"
            elif expected_str in actual_str or actual_str in expected_str:
                match = "Yes (Fuzzy)"
                
            if match.startswith("Yes"):
                stats[path_type]["matched"] += 1
            stats[path_type]["total"] += 1
                
            print(f"| {gt_key} | {expected_val} | {actual_val} | {match} | {conf:.2f} |")
        print("\n")

    print("### Summary")
    t_match, t_tot = stats['text']['matched'], stats['text']['total']
    v_match, v_tot = stats['vision']['matched'], stats['vision']['total']
    
    print(f"- **Text Path Accuracy**: {t_match}/{t_tot} ({(t_match/t_tot)*100:.1f}%)" if t_tot else "- **Text Path Accuracy**: N/A")
    print(f"- **Vision Path Accuracy**: {v_match}/{v_tot} ({(v_match/v_tot)*100:.1f}%)" if v_tot else "- **Vision Path Accuracy**: N/A")

if __name__ == "__main__":
    asyncio.run(main())

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

    # Gather first 10 documents
    docs = []
    for app in applicants:
        for doc in app.get("documents", []):
            docs.append({
                "app_id": app["application_id"],
                "doc_type": doc["type"],
                "path": doc["path"],
                "expected": doc.get("expected_extraction", {})
            })
            if len(docs) >= 10:
                break
        if len(docs) >= 10:
            break

    print(f"## Phase B Evidence: Real Groq Provider ({settings.GROQ_TEXT_MODEL}, {settings.GROQ_VISION_MODEL})")
    print(f"**Command executed:** `$env:PYTHONPATH=\".\"; python scripts/phase_b_evidence.py`\n")
    
    for i, doc in enumerate(docs):
        print(f"### Document {i+1}: {doc['doc_type']}")
        print(f"- **Path**: `{doc['path']}`")
        
        doc_type = DocumentType(doc["doc_type"])
        res = await extraction_service.extract_document(doc_type, file_path=doc['path'])
        
        print(f"- **Extraction Method**: `{res.extraction_method}` (Vision Path Used: {'Yes' if 'vision' in res.extraction_method else 'No'})")
        
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
            
        print("\n| Field | Expected Value | Actual Value | Confidence |")
        print("|-------|----------------|--------------|------------|")
        
        expected = doc['expected']
        
        for k, expected_val in expected.items():
            if k in actual_data and isinstance(actual_data[k], dict):
                actual_val = actual_data[k].get("value")
                conf = actual_data[k].get("confidence", 0.0)
                print(f"| {k} | {expected_val} | {actual_val} | {conf:.2f} |")
            else:
                actual_val = actual_data.get(k)
                print(f"| {k} | {expected_val} | {actual_val} | N/A |")
        print("\n")

if __name__ == "__main__":
    asyncio.run(main())

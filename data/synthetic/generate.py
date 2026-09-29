"""
Synthetic data generator — Phase 2.

ALL DATA IS 100% SYNTHETIC. Faker generates every name, address, ID number,
and income figure. No real PII is used anywhere.

Design decision: we pre-define a set of SCENARIOS with explicit labels so the
evaluation harness (Phase 8) can compare extracted values against ground truth.
Random generation alone doesn't give you labelled ground truth.

Scenarios:
  CLEAN          — everything passes, should auto-approve
  LOW_INCOME     — income below threshold, should auto-reject
  EXPIRED_ID     — government ID past expiry, should auto-reject
  NAME_MISMATCH  — name on ID differs from application, should human-review
  TOO_YOUNG      — applicant under 18, should auto-reject
  TOO_OLD        — applicant over 70, should auto-reject
  LOAN_TOO_HIGH  — loan > 5x annual income, should auto-reject
  MISSING_DOC    — no proof of income uploaded, should request info
  LOW_CONFIDENCE — we simulate a blurry/damaged document (extraction note added)
  BORDERLINE     — all rules pass but confidence scores will be at the threshold

Run:  python data/synthetic/generate.py
Output: data/synthetic/applicants.json   (ground truth labels)
        data/synthetic/docs/<app_id>/    (one folder per applicant with PDFs)
"""
import json
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# pyrefly: ignore [missing-import]
from faker import Faker

# ---------------------------------------------------------------------------
# Add project root to sys.path so we can import core.config if needed
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

fake = Faker("en_US")
Faker.seed(42)           # deterministic output — same data every run
random.seed(42)

OUTPUT_DIR = Path(__file__).parent
DOCS_DIR = OUTPUT_DIR / "docs"
DOCS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Constants (match .env.example defaults)
# ---------------------------------------------------------------------------
MIN_AGE = 18
MAX_AGE = 70
MIN_MONTHLY_INCOME = 1500.0
MAX_LOAN_TO_INCOME_RATIO = 5.0   # loan <= 5 * annual_income
ID_EXPIRY_BUFFER_DAYS = 30
TODAY = date.today()


# ---------------------------------------------------------------------------
# PDF generation helpers
# ---------------------------------------------------------------------------
def _make_pdf(path: Path, lines: list[str], watermark: str = "") -> None:
    """
    Generate a minimal PDF using ReportLab.
    Each string in `lines` becomes one line of text.
    `watermark` adds a diagonal red annotation (simulates damage/blur flag).
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas

        path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4

        # Body text
        y = height - 80
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, lines[0])  # document title
        c.setFont("Helvetica", 11)
        for line in lines[1:]:
            y -= 22
            if y < 80:
                c.showPage()
                y = height - 80
            c.drawString(50, y, line)

        # Watermark for LOW_CONFIDENCE scenario
        if watermark:
            c.saveState()
            c.setFont("Helvetica-Bold", 40)
            c.setFillColor(colors.red)
            c.setFillAlpha(0.3)
            c.translate(width / 2, height / 2)
            c.rotate(45)
            c.drawCentredString(0, 0, watermark)
            c.restoreState()

        c.save()
    except ImportError:
        # Fallback: write a plain text file if reportlab is not installed
        path = path.with_suffix(".txt")
        path.write_text("\n".join(lines))


def _make_id_pdf(path: Path, name: str, dob: date, id_number: str,
                 address: str, expiry: date, watermark: str = "") -> None:
    _make_pdf(path, [
        "GOVERNMENT ISSUED ID — SYNTHETIC (NOT REAL)",
        f"Full Name:    {name}",
        f"Date of Birth: {dob.isoformat()}",
        f"ID Number:    {id_number}",
        f"Address:      {address}",
        f"Expiry Date:  {expiry.isoformat()}",
        "",
        "*** THIS IS SYNTHETIC TEST DATA — NOT A REAL DOCUMENT ***",
    ], watermark=watermark)


def _make_income_pdf(path: Path, name: str, employer: str,
                     monthly_income: float, pay_period: str,
                     watermark: str = "") -> None:
    annual = monthly_income * 12
    _make_pdf(path, [
        "PROOF OF INCOME — SYNTHETIC PAYSLIP",
        f"Employee Name:  {name}",
        f"Employer:       {employer}",
        f"Pay Period:     {pay_period}",
        f"Monthly Income: ${monthly_income:,.2f}",
        f"Annual Income:  ${annual:,.2f}",
        "",
        "*** THIS IS SYNTHETIC TEST DATA — NOT A REAL DOCUMENT ***",
    ], watermark=watermark)


def _make_address_pdf(path: Path, name: str, address: str,
                      utility_company: str, bill_date: date) -> None:
    _make_pdf(path, [
        "ADDRESS PROOF — SYNTHETIC UTILITY BILL",
        f"Account Holder: {name}",
        f"Service Address: {address}",
        f"Utility Company: {utility_company}",
        f"Bill Date:       {bill_date.isoformat()}",
        f"Amount Due:      ${random.uniform(50, 300):.2f}",
        "",
        "*** THIS IS SYNTHETIC TEST DATA — NOT A REAL DOCUMENT ***",
    ])


# ---------------------------------------------------------------------------
# Applicant factories per scenario
# ---------------------------------------------------------------------------

def _clean_applicant(app_id: str) -> dict[str, Any]:
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=25, maximum_age=55)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=random.randint(60, 365 * 3))
    monthly_income = round(random.uniform(3000, 8000), 2)
    loan_amount = round(random.uniform(5000, monthly_income * 12 * 2), 2)
    employer = fake.company()

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, employer, monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      fake.company() + " Utilities", TODAY - timedelta(days=15))

    return {
        "application_id": app_id,
        "scenario": "CLEAN",
        "expected_decision": "AUTO_APPROVED",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": random.choice(["Home renovation", "Debt consolidation", "Auto purchase"]),
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": round(monthly_income * 12, 2),
            "employer": employer,
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _low_income_applicant(app_id: str) -> dict[str, Any]:
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=25, maximum_age=55)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=random.randint(60, 365))
    monthly_income = round(random.uniform(500, 1400), 2)   # below threshold
    loan_amount = round(random.uniform(5000, 20000), 2)
    employer = fake.company()

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, employer, monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      fake.company() + " Utilities", TODAY - timedelta(days=10))

    return {
        "application_id": app_id,
        "scenario": "LOW_INCOME",
        "expected_decision": "AUTO_REJECTED",
        "expected_rejection_reason": "monthly_income_below_minimum",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Medical expenses",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": round(monthly_income * 12, 2),
            "employer": employer,
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _expired_id_applicant(app_id: str) -> dict[str, Any]:
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=25, maximum_age=55)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    # Expired: either already past, or within the buffer window
    id_expiry = TODAY - timedelta(days=random.randint(1, 180))
    monthly_income = round(random.uniform(3000, 7000), 2)
    loan_amount = round(random.uniform(5000, monthly_income * 6), 2)
    employer = fake.company()

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, employer, monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      fake.company() + " Utilities", TODAY - timedelta(days=5))

    return {
        "application_id": app_id,
        "scenario": "EXPIRED_ID",
        "expected_decision": "AUTO_REJECTED",
        "expected_rejection_reason": "government_id_expired",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Business startup",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": round(monthly_income * 12, 2),
            "employer": employer,
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _name_mismatch_applicant(app_id: str) -> dict[str, Any]:
    """Name on ID differs from application form — human review needed."""
    name_on_form = fake.name()
    name_on_id = fake.name()    # deliberately different
    dob = fake.date_of_birth(minimum_age=25, maximum_age=55)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=random.randint(60, 365))
    monthly_income = round(random.uniform(3000, 6000), 2)
    loan_amount = round(random.uniform(5000, monthly_income * 10), 2)
    employer = fake.company()

    doc_dir = DOCS_DIR / app_id
    # ID has a DIFFERENT name from the application form
    _make_id_pdf(doc_dir / "government_id.pdf", name_on_id, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name_on_form, employer, monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name_on_form, address,
                      fake.company() + " Utilities", TODAY - timedelta(days=7))

    return {
        "application_id": app_id,
        "scenario": "NAME_MISMATCH",
        "expected_decision": "HUMAN_REVIEW",
        "expected_flag": "name_mismatch",
        "applicant_name": name_on_form,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Education",
        "ground_truth": {
            "name_on_form": name_on_form,
            "name_on_id": name_on_id,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": round(monthly_income * 12, 2),
            "employer": employer,
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _too_young_applicant(app_id: str) -> dict[str, Any]:
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=14, maximum_age=17)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=200)
    monthly_income = round(random.uniform(1600, 3000), 2)
    loan_amount = round(random.uniform(1000, 5000), 2)

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, "Part-time employer", monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      "City Gas", TODAY - timedelta(days=20))

    return {
        "application_id": app_id,
        "scenario": "TOO_YOUNG",
        "expected_decision": "AUTO_REJECTED",
        "expected_rejection_reason": "applicant_under_minimum_age",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Personal",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": round(monthly_income * 12, 2),
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _too_old_applicant(app_id: str) -> dict[str, Any]:
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=71, maximum_age=90)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=180)
    monthly_income = round(random.uniform(2000, 5000), 2)
    loan_amount = round(random.uniform(5000, 15000), 2)

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, "Retirement Fund", monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      "Senior Living Utilities", TODAY - timedelta(days=12))

    return {
        "application_id": app_id,
        "scenario": "TOO_OLD",
        "expected_decision": "AUTO_REJECTED",
        "expected_rejection_reason": "applicant_over_maximum_age",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Home repair",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": round(monthly_income * 12, 2),
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _loan_too_high_applicant(app_id: str) -> dict[str, Any]:
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=25, maximum_age=55)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=random.randint(90, 365))
    monthly_income = round(random.uniform(2000, 4000), 2)
    annual_income = monthly_income * 12
    # Loan > 5x annual income
    loan_amount = round(annual_income * random.uniform(6, 10), 2)
    employer = fake.company()

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, employer, monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      fake.company() + " Power", TODAY - timedelta(days=8))

    return {
        "application_id": app_id,
        "scenario": "LOAN_TOO_HIGH",
        "expected_decision": "AUTO_REJECTED",
        "expected_rejection_reason": "loan_exceeds_income_ratio",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Real estate investment",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": annual_income,
            "employer": employer,
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _missing_doc_applicant(app_id: str) -> dict[str, Any]:
    """No proof of income uploaded — rules engine flags MISSING_DOCUMENT."""
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=25, maximum_age=55)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=random.randint(90, 365))
    loan_amount = round(random.uniform(5000, 20000), 2)

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      "Metro Utilities", TODAY - timedelta(days=18))
    # NOTE: no proof_of_income.pdf generated — deliberately missing

    return {
        "application_id": app_id,
        "scenario": "MISSING_DOC",
        "expected_decision": "AUTO_REJECTED",
        "expected_rejection_reason": "missing_required_document_proof_of_income",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Vehicle purchase",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": None,   # missing
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            # No PROOF_OF_INCOME entry
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _low_confidence_applicant(app_id: str) -> dict[str, Any]:
    """
    Simulates a damaged/blurry document by adding a watermark to the PDFs.
    The LLM extraction service will detect the annotation and lower confidence.
    In Phase 3 we add a special note in the document to trigger sub-threshold confidence.
    """
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=25, maximum_age=55)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    id_expiry = TODAY + timedelta(days=random.randint(90, 365))
    monthly_income = round(random.uniform(3000, 6000), 2)
    loan_amount = round(random.uniform(5000, monthly_income * 8), 2)
    employer = fake.company()

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry,
                 watermark="DAMAGED")
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, employer, monthly_income,
                     f"{fake.month_name()} {TODAY.year}", watermark="DAMAGED")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      fake.company() + " Power", TODAY - timedelta(days=6))

    return {
        "application_id": app_id,
        "scenario": "LOW_CONFIDENCE",
        "expected_decision": "HUMAN_REVIEW",
        "expected_flag": "low_extraction_confidence",
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Home purchase",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": round(monthly_income * 12, 2),
            "employer": employer,
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


def _borderline_applicant(app_id: str) -> dict[str, Any]:
    """
    All rules pass but income is exactly at the minimum and loan is at max ratio.
    Good stress test for boundary conditions in the rules engine.
    """
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=19, maximum_age=69)
    address = fake.address().replace("\n", ", ")
    id_number = fake.bothify("ID-########")
    # Expiry just outside the buffer window (valid but close)
    id_expiry = TODAY + timedelta(days=ID_EXPIRY_BUFFER_DAYS + 1)
    monthly_income = MIN_MONTHLY_INCOME + 0.01   # just above minimum
    annual_income = round(monthly_income * 12, 2)
    # Loan at exactly 5x annual income (the boundary)
    loan_amount = round(annual_income * MAX_LOAN_TO_INCOME_RATIO, 2)
    employer = fake.company()

    doc_dir = DOCS_DIR / app_id
    _make_id_pdf(doc_dir / "government_id.pdf", name, dob, id_number, address, id_expiry)
    _make_income_pdf(doc_dir / "proof_of_income.pdf", name, employer, monthly_income,
                     f"{fake.month_name()} {TODAY.year}")
    _make_address_pdf(doc_dir / "address_proof.pdf", name, address,
                      fake.company() + " Gas", TODAY - timedelta(days=20))

    return {
        "application_id": app_id,
        "scenario": "BORDERLINE",
        "expected_decision": "AUTO_APPROVED",   # boundary passes, should approve
        "applicant_name": name,
        "applicant_email": fake.email(),
        "requested_loan_amount": loan_amount,
        "loan_purpose": "Debt consolidation",
        "ground_truth": {
            "name": name,
            "dob": dob.isoformat(),
            "id_number": id_number,
            "address": address,
            "id_expiry": id_expiry.isoformat(),
            "monthly_income": monthly_income,
            "annual_income": annual_income,
            "employer": employer,
        },
        "documents": [
            {"type": "GOVERNMENT_ID", "path": str(doc_dir / "government_id.pdf")},
            {"type": "PROOF_OF_INCOME", "path": str(doc_dir / "proof_of_income.pdf")},
            {"type": "ADDRESS_PROOF", "path": str(doc_dir / "address_proof.pdf")},
        ],
    }


# ---------------------------------------------------------------------------
# Scenario distribution (targeting 50+ applicants for Phase 8 evaluation)
# ---------------------------------------------------------------------------
SCENARIO_DISTRIBUTION = [
    ("CLEAN",          20, _clean_applicant),
    ("LOW_INCOME",      6, _low_income_applicant),
    ("EXPIRED_ID",      6, _expired_id_applicant),
    ("NAME_MISMATCH",   5, _name_mismatch_applicant),
    ("TOO_YOUNG",       3, _too_young_applicant),
    ("TOO_OLD",         3, _too_old_applicant),
    ("LOAN_TOO_HIGH",   5, _loan_too_high_applicant),
    ("MISSING_DOC",     4, _missing_doc_applicant),
    ("LOW_CONFIDENCE",  5, _low_confidence_applicant),
    ("BORDERLINE",      4, _borderline_applicant),
]
# Total: 61 applicants


def generate_all() -> list[dict]:
    applicants = []
    counters: dict[str, int] = {}

    for scenario, count, factory in SCENARIO_DISTRIBUTION:
        counters[scenario] = 0
        for _ in range(count):
            app_id = str(uuid.uuid4())
            record = factory(app_id)
            applicants.append(record)
            counters[scenario] += 1
            print(f"  OK {scenario:20s} [{counters[scenario]:02d}/{count}]  {app_id[:8]}...")

    return applicants


def main() -> None:
    print("=" * 60)
    print("Synthetic data generator — ALL DATA IS FAKE")
    print(f"Output dir: {OUTPUT_DIR}")
    print("=" * 60)

    applicants = generate_all()

    # Write ground truth JSON
    output_path = OUTPUT_DIR / "applicants.json"
    with open(output_path, "w") as f:
        json.dump(applicants, f, indent=2, default=str)

    print()
    print(f"[DONE] Generated {len(applicants)} synthetic applicants")
    print(f"[GT]   Ground truth: {output_path}")
    print(f"[DOC]  Documents:    {DOCS_DIR}/")
    print()

    # Summary stats
    by_scenario: dict[str, int] = {}
    by_decision: dict[str, int] = {}
    for a in applicants:
        by_scenario[a["scenario"]] = by_scenario.get(a["scenario"], 0) + 1
        by_decision[a["expected_decision"]] = by_decision.get(a["expected_decision"], 0) + 1

    print("Scenario breakdown:")
    for s, c in by_scenario.items():
        print(f"  {s:25s}: {c}")
    print()
    print("Expected decision breakdown:")
    for d, c in by_decision.items():
        print(f"  {d:25s}: {c}")


if __name__ == "__main__":
    main()

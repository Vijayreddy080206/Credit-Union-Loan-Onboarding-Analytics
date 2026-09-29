"""
Phase 2 tests — verifies the synthetic data generator output structure and
scenario coverage without regenerating files (reads the output JSON if it
exists, or imports the generator functions directly).

Design note: we test the generator functions, not the file output, so tests
run fast without file I/O. The integration check (does applicants.json exist?)
is a separate, slower test you run manually after `python data/synthetic/generate.py`.
"""
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

# pyrefly: ignore [missing-import]
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestScenarioDistribution:
    """Verifies the scenario distribution adds up correctly."""

    def test_total_applicant_count(self):
        from data.synthetic.generate import SCENARIO_DISTRIBUTION
        total = sum(count for _, count, _ in SCENARIO_DISTRIBUTION)
        assert total >= 50, f"Need ≥50 applicants for evaluation harness, got {total}"

    def test_all_expected_decisions_present(self):
        from data.synthetic.generate import SCENARIO_DISTRIBUTION
        # Run each factory with a fake app_id, patching _make_pdf to avoid file I/O
        decisions = set()
        with patch("data.synthetic.generate._make_pdf"):
            for _, count, factory in SCENARIO_DISTRIBUTION:
                if count > 0:
                    record = factory(str(uuid.uuid4()))
                    decisions.add(record["expected_decision"])

        required = {"AUTO_APPROVED", "AUTO_REJECTED", "HUMAN_REVIEW"}
        assert required.issubset(decisions), f"Missing decisions: {required - decisions}"

    def test_each_scenario_has_required_fields(self):
        from data.synthetic.generate import SCENARIO_DISTRIBUTION
        required_keys = {
            "application_id", "scenario", "expected_decision",
            "applicant_name", "applicant_email", "requested_loan_amount",
            "ground_truth", "documents",
        }
        with patch("data.synthetic.generate._make_pdf"):
            for scenario_name, count, factory in SCENARIO_DISTRIBUTION:
                if count > 0:
                    record = factory(str(uuid.uuid4()))
                    missing = required_keys - set(record.keys())
                    assert not missing, f"Scenario {scenario_name} missing keys: {missing}"

    def test_clean_scenario_has_three_documents(self):
        from data.synthetic.generate import _clean_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _clean_applicant(str(uuid.uuid4()))
        assert len(record["documents"]) == 3
        doc_types = {d["type"] for d in record["documents"]}
        assert doc_types == {"GOVERNMENT_ID", "PROOF_OF_INCOME", "ADDRESS_PROOF"}

    def test_missing_doc_scenario_has_two_documents(self):
        from data.synthetic.generate import _missing_doc_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _missing_doc_applicant(str(uuid.uuid4()))
        doc_types = {d["type"] for d in record["documents"]}
        assert "PROOF_OF_INCOME" not in doc_types, "Missing doc scenario should not have income doc"
        assert len(record["documents"]) == 2


class TestGroundTruthStructure:
    """Ground truth fields must be present and internally consistent."""

    def test_clean_ground_truth_has_all_fields(self):
        from data.synthetic.generate import _clean_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _clean_applicant(str(uuid.uuid4()))
        gt = record["ground_truth"]
        for field in ["name", "dob", "id_number", "address", "id_expiry",
                      "monthly_income", "annual_income", "employer"]:
            assert field in gt, f"Missing ground truth field: {field}"

    def test_annual_income_is_12x_monthly(self):
        from data.synthetic.generate import _clean_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _clean_applicant(str(uuid.uuid4()))
        gt = record["ground_truth"]
        assert abs(gt["annual_income"] - gt["monthly_income"] * 12) < 0.01

    def test_name_mismatch_has_two_distinct_names(self):
        from data.synthetic.generate import _name_mismatch_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _name_mismatch_applicant(str(uuid.uuid4()))
        gt = record["ground_truth"]
        assert "name_on_form" in gt
        assert "name_on_id" in gt
        # The whole point of this scenario: they must be different
        assert gt["name_on_form"] != gt["name_on_id"]

    def test_too_young_dob_makes_applicant_under_18(self):
        from datetime import date
        from data.synthetic.generate import _too_young_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _too_young_applicant(str(uuid.uuid4()))
        dob = date.fromisoformat(record["ground_truth"]["dob"])
        today = date.today()
        age = (today - dob).days // 365
        assert age < 18, f"Expected age < 18, got {age}"

    def test_too_old_dob_makes_applicant_over_70(self):
        from datetime import date
        from data.synthetic.generate import _too_old_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _too_old_applicant(str(uuid.uuid4()))
        dob = date.fromisoformat(record["ground_truth"]["dob"])
        today = date.today()
        age = (today - dob).days // 365
        assert age > 70, f"Expected age > 70, got {age}"

    def test_expired_id_is_in_the_past(self):
        from datetime import date
        from data.synthetic.generate import _expired_id_applicant
        with patch("data.synthetic.generate._make_pdf"):
            record = _expired_id_applicant(str(uuid.uuid4()))
        expiry = date.fromisoformat(record["ground_truth"]["id_expiry"])
        assert expiry < date.today(), "Expired ID scenario must have past expiry date"

    def test_loan_too_high_exceeds_5x_annual(self):
        from data.synthetic.generate import _loan_too_high_applicant, MAX_LOAN_TO_INCOME_RATIO
        with patch("data.synthetic.generate._make_pdf"):
            record = _loan_too_high_applicant(str(uuid.uuid4()))
        annual = record["ground_truth"]["annual_income"]
        loan = record["requested_loan_amount"]
        ratio = loan / annual
        assert ratio > MAX_LOAN_TO_INCOME_RATIO, f"Loan/income ratio {ratio:.2f} must exceed {MAX_LOAN_TO_INCOME_RATIO}"

    def test_low_income_is_below_minimum(self):
        from data.synthetic.generate import _low_income_applicant, MIN_MONTHLY_INCOME
        with patch("data.synthetic.generate._make_pdf"):
            record = _low_income_applicant(str(uuid.uuid4()))
        monthly = record["ground_truth"]["monthly_income"]
        assert monthly < MIN_MONTHLY_INCOME, f"Low income {monthly} must be below {MIN_MONTHLY_INCOME}"

    def test_borderline_income_is_above_minimum(self):
        from data.synthetic.generate import _borderline_applicant, MIN_MONTHLY_INCOME
        with patch("data.synthetic.generate._make_pdf"):
            record = _borderline_applicant(str(uuid.uuid4()))
        monthly = record["ground_truth"]["monthly_income"]
        assert monthly >= MIN_MONTHLY_INCOME, f"Borderline income {monthly} must be ≥ {MIN_MONTHLY_INCOME}"


class TestOutputFileStructure:
    """Checks applicants.json exists and is valid after the generator has run.
    Skip if not yet generated (run `python data/synthetic/generate.py` first).
    """

    def test_applicants_json_is_valid_if_exists(self):
        import json
        json_path = Path(__file__).parent.parent / "data" / "synthetic" / "applicants.json"
        if not json_path.exists():
            pytest.skip("applicants.json not yet generated — run the generator first")

        with open(json_path) as f:
            applicants = json.load(f)

        assert isinstance(applicants, list)
        assert len(applicants) >= 50

        for a in applicants:
            assert "application_id" in a
            assert "scenario" in a
            assert "expected_decision" in a
            assert "ground_truth" in a

"""The synthetic demo PDFs must keep reproducing each persona's key findings
when uploaded through the real ingest -> extract -> evaluate pipeline."""

from pathlib import Path

import pytest

from clinic.visit import run_visit

DOCS = Path(__file__).resolve().parents[2] / "demo_docs"

CASES = {
    "mei": (["mei_resume.pdf", "mei_financials.pdf"], ["us-federal", "hong-kong", "cross-border"],
            {"us.fed.fbar": "required", "us.fed.3520": "required"}),
    "luis": (["luis_resume.pdf", "luis_financials.pdf"], ["us-federal", "massachusetts"],
             {"us.fed.schedule_c": "required", "us.fed.tips": "required", "ma.dor.part_year": "required"}),
    "sichuan": (["sichuan_profile.pdf", "sichuan_financials.pdf"], ["us-federal", "massachusetts"],
                {"ma.dor.meals": "required"}),
    "nimbus": (["nimbus_profile.pdf", "nimbus_financials.pdf"], ["us-federal", "massachusetts", "other-us-states"],
               {"us.fed.1120": "required", "ma.dor.saas_sales": "required"}),
    "nori": (["nori_profile.pdf", "nori_financials.pdf"], ["us-federal", "cross-border"],
             {"us.fed.1120": "required", "us.fed.5471": "likely", "us.fed.5472": "likely"}),
    "chen": (["chen_background.pdf", "chen_financials.pdf"], ["us-federal"],
             {"us.fed.founder_public": "check"}),
}


@pytest.mark.parametrize("pid", CASES)
def test_demo_pdf_roundtrip(pid):
    names, jurs, expect = CASES[pid]
    if not DOCS.is_dir():
        pytest.skip("demo_docs not generated (python3 make_demo_pdfs.py)")
    files = [(n, (DOCS / n).read_bytes()) for n in names]
    out = run_visit(text="", live=True, jurisdictions=jurs, files=files)
    got = {f.rule_id: f.status.value for f in out.findings}
    for rule, status in expect.items():
        assert got.get(rule) == status, f"{pid}: {rule} expected {status}, got {got.get(rule)}"


def test_mei_pdfs_fbar_aggregate_is_confirmed():
    if not DOCS.is_dir():
        pytest.skip("demo_docs not generated")
    files = [(n, (DOCS / n).read_bytes()) for n in ["mei_resume.pdf", "mei_financials.pdf"]]
    out = run_visit(text="", live=True, jurisdictions=["us-federal"], files=files)
    assert float(out.profile.foreign_account_total()) == 15000
    fbar = next(f for f in out.findings if f.rule_id == "us.fed.fbar")
    assert fbar.confidence == "confirmed"

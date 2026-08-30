"""One zip per persona (both PDFs + the xlsx) must reproduce the key findings
when uploaded as a single file — the easy-upload demo path."""

from pathlib import Path

import pytest

from clinic.documents import ingest_files
from clinic.visit import run_visit

DOCS = Path(__file__).resolve().parents[2] / "demo_docs"

CASES = {
    "mei": ("mei_case_file.zip", ["us-federal", "hong-kong", "cross-border"],
            {"us.fed.fbar": "required", "us.fed.3520": "required"}),
    "luis": ("luis_case_file.zip", ["us-federal", "massachusetts"],
             {"us.fed.schedule_c": "required", "us.fed.tips": "required", "ma.dor.part_year": "required"}),
    "sichuan": ("sichuan_case_file.zip", ["us-federal", "massachusetts"],
                {"ma.dor.meals": "required"}),
    "nimbus": ("nimbus_case_file.zip", ["us-federal", "massachusetts", "other-us-states"],
               {"us.fed.1120": "required", "ma.dor.saas_sales": "required"}),
    "nori": ("nori_case_file.zip", ["us-federal", "cross-border"],
             {"us.fed.1120": "required", "us.fed.5471": "likely", "us.fed.5472": "likely"}),
    "chen": ("chen_case_file.zip", ["us-federal"],
             {"us.fed.founder_public": "check"}),
}


def _need(name: str) -> bytes:
    if not (DOCS / name).exists():
        pytest.skip(f"{name} not generated (python3 make_demo_zips.py)")
    return (DOCS / name).read_bytes()


@pytest.mark.parametrize("pid", CASES)
def test_demo_zip_roundtrip(pid):
    name, jurs, expect = CASES[pid]
    out = run_visit(text="", live=True, jurisdictions=jurs, files=[(name, _need(name))])
    got = {f.rule_id: f.status.value for f in out.findings}
    for rule, status in expect.items():
        assert got.get(rule) == status, f"{pid}: {rule} expected {status}, got {got.get(rule)}"


def test_zip_lists_all_three_member_documents():
    data = _need("mei_case_file.zip")
    text, docs = ingest_files([("mei_case_file.zip", data)])
    names = {d.name for d in docs}
    assert names == {
        "mei_case_file.zip/mei_resume.pdf",
        "mei_case_file.zip/mei_financials.pdf",
        "mei_case_file.zip/mei_worksheet.xlsx",
    }
    kinds = {d.kind for d in docs}
    assert kinds == {"pdf", "spreadsheet"}

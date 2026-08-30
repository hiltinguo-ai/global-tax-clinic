"""The synthetic demo workbooks must keep reproducing each persona's key
findings when uploaded alone through ingest -> extract -> evaluate."""

from pathlib import Path

import pytest

from clinic.documents import ingest_files
from clinic.visit import run_visit

DOCS = Path(__file__).resolve().parents[2] / "demo_docs"

CASES = {
    "mei": ("mei_worksheet.xlsx", ["us-federal", "hong-kong", "cross-border"],
            {"us.fed.fbar": "required", "us.fed.3520": "required"}),
    "luis": ("luis_worksheet.xlsx", ["us-federal", "massachusetts"],
             {"us.fed.schedule_c": "required", "us.fed.tips": "required", "ma.dor.part_year": "required"}),
    "sichuan": ("sichuan_books.xlsx", ["us-federal", "massachusetts"],
                {"ma.dor.meals": "required"}),
    "nimbus": ("nimbus_revenue.xlsx", ["us-federal", "massachusetts", "other-us-states"],
               {"us.fed.1120": "required", "ma.dor.saas_sales": "required"}),
    "nori": ("nori_captable.xlsx", ["us-federal", "cross-border"],
             {"us.fed.1120": "required", "us.fed.5471": "likely", "us.fed.5472": "likely"}),
    "chen": ("chen_trust.xlsx", ["us-federal"],
             {"us.fed.founder_public": "check", "us.fed.fbar": "required", "us.fed.1041": "required"}),
}


def _need(name: str) -> bytes:
    if not (DOCS / name).exists():
        pytest.skip(f"{name} not generated (python3 make_demo_sheets.py demo_docs)")
    return (DOCS / name).read_bytes()


@pytest.mark.parametrize("pid", CASES)
def test_demo_sheet_roundtrip(pid):
    name, jurs, expect = CASES[pid]
    out = run_visit(text="", live=True, jurisdictions=jurs, files=[(name, _need(name))])
    got = {f.rule_id: f.status.value for f in out.findings}
    for rule, status in expect.items():
        assert got.get(rule) == status, f"{pid}: {rule} expected {status}, got {got.get(rule)}"


def test_xlsx_ingest_reads_cached_formula_totals():
    data = _need("mei_worksheet.xlsx")
    text, docs = ingest_files([("mei_worksheet.xlsx", data)])
    assert docs and docs[0].kind == "spreadsheet"
    assert "15000" in text  # the =SUM aggregate, recalculated and cached


def test_chen_sheet_cached_formula_totals():
    data = _need("chen_trust.xlsx")
    text, docs = ingest_files([("chen_trust.xlsx", data)])
    assert docs and docs[0].kind == "spreadsheet"
    assert "2000000" in text.replace(",", "")
    assert "8640000" in text.replace(",", "")
    out = run_visit(text="", live=True, jurisdictions=["us-federal"],
                    files=[("chen_trust.xlsx", data)])
    assert float(out.profile.foreign_account_total()) == 2_000_000


def test_nimbus_sheet_revenue_attribution_is_per_row():
    data = _need("nimbus_revenue.xlsx")
    out = run_visit(text="", live=True, jurisdictions=["us-federal", "massachusetts"],
                    files=[("nimbus_revenue.xlsx", data)])
    p = out.profile
    assert float(p.state_revenue("MA")) == 420000
    assert float(p.state_revenue("NY")) == 240000

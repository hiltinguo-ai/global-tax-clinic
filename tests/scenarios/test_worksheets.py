"""Every persona must produce at least one computable worksheet line — the
accountant desk applies pack rates/thresholds to amounts already in the file."""

from pathlib import Path

import pytest

from clinic.visit import run_visit

DOCS = Path(__file__).resolve().parents[2] / "demo_docs"

GOLD = {
    "mei": (["us-federal", "hong-kong", "cross-border"],
            ["Foreign account aggregate", "Foreign gifts received"]),
    "luis": (["us-federal", "massachusetts"],
             ["Illustrated SE tax", "Wage and tip base", "Part-year residency day split"]),
    "sichuan": (["us-federal", "massachusetts"], ["Illustrated MA meals tax"]),
    "nimbus": (["us-federal", "massachusetts", "other-us-states"],
               ["MA single sales factor", "Economic nexus screen"]),
    "nori": (["us-federal", "massachusetts", "cross-border"],
             ["83(b) statutory window", "25% foreign-owner test"]),
    "chen": (["us-federal"], ["Concentrated founder position", "Foreign account aggregate"]),
}


def _names(out) -> list[str]:
    return [w.name for w in out.agency.worksheet]


@pytest.mark.parametrize("pid", GOLD)
def test_gold_persona_has_computable_worksheet(pid):
    jurs, expected = GOLD[pid]
    out = run_visit(text="", persona_id=pid, jurisdictions=jurs)
    names = _names(out)
    assert "No computable worksheet" not in names
    for want in expected:
        assert any(want in n for n in names), f"{pid}: missing worksheet line {want!r} in {names}"


@pytest.mark.parametrize("pid", GOLD)
def test_zip_upload_has_computable_worksheet(pid):
    jurs, _ = GOLD[pid]
    name = f"{pid}_case_file.zip"
    if not (DOCS / name).exists():
        pytest.skip("zips not generated")
    out = run_visit(text="", live=True, jurisdictions=jurs, files=[(name, (DOCS / name).read_bytes())])
    names = _names(out)
    assert "No computable worksheet" not in names
    assert names, f"{pid}: no worksheet lines at all"


def test_worksheet_values_are_exact():
    out = run_visit(text="", persona_id="mei", jurisdictions=["us-federal"])
    agg = next(w for w in out.agency.worksheet if "aggregate" in w.name.lower())
    assert agg.result == "15,000.00"
    out = run_visit(text="", persona_id="nori", jurisdictions=["us-federal"])
    win = next(w for w in out.agency.worksheet if "83(b)" in w.name)
    assert win.result == "2026-08-31"  # grant 2026-08-01 + 30 statutory days


def test_check_finding_never_yields_illustrated_tax():
    # nimbus is not a restaurant; ma.dor.meals can only be a tri-logic "check"
    name = "nimbus_case_file.zip"
    if not (DOCS / name).exists():
        pytest.skip("zips not generated")
    out = run_visit(text="", live=True, jurisdictions=["us-federal", "massachusetts"],
                    files=[(name, (DOCS / name).read_bytes())])
    assert not any("meals" in w.name.lower() for w in out.agency.worksheet)
    assert not any("foreign-owner" in w.name for w in out.agency.worksheet)  # "no foreign subsidiaries" stated

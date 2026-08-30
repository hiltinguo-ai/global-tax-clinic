from clinic.agency import run_agency
from clinic.engine import evaluate
from clinic.extract import extract
from clinic.personas import PERSONA_TRANSCRIPTS, profile_nimbus, profile_sichuan


def test_nimbus_counsel_confirms_ma_and_reviews_others():
    findings, _ = evaluate(profile_nimbus())
    ids = {f.rule_id for f in findings}
    assert "ma.dor.saas_sales" in ids
    assert "ma.dor.excise" in ids
    assert "us.fed.1120" in ids
    assert "us.state.economic_nexus_review" in ids
    docket = run_agency(profile_nimbus(), findings)
    yes = [n for n in docket.nexus if n.nexus == "YES"]
    review = [n for n in docket.nexus if n.nexus == "REVIEW"]
    assert any(n.jurisdiction == "MA" for n in yes)
    assert {n.jurisdiction for n in review} >= {"NY", "CA", "TX", "IL"}
    factor = next(w for w in docket.worksheet if "sales factor" in w.name.lower())
    assert "33.60%" in factor.result
    sales = next(w for w in docket.worksheet if "sales tax" in w.name.lower())
    assert "26,250.00" in sales.result
    assert any(c.form == "Form 355" for c in docket.calendar)
    assert docket.review.role == "review"
    assert "REVIEW" in docket.review.summary


def test_nimbus_extractor():
    profile, source = extract(PERSONA_TRANSCRIPTS["nimbus"]["text_en"], persona_id="nimbus")
    assert source.startswith("persona:nimbus")
    assert profile.industry == "saas"
    assert profile.state_revenue("MA") == profile.revenue_by_state[0].amount_usd


def test_live_intake_does_not_snap_to_gold_persona():
    _, source = extract(PERSONA_TRANSCRIPTS["nimbus"]["text_en"], live=True)
    assert not source.startswith("persona:")
    assert source in {"heuristic", "ollama:qwen3.5:4b", "ollama:qwen3.5:4b+heuristic"}


def test_restaurant_does_not_take_saas_rule():
    findings, _ = evaluate(profile_sichuan())
    assert "ma.dor.saas_sales" not in {f.rule_id for f in findings}
    assert "ma.dor.meals" in {f.rule_id for f in findings}


def test_gst_illustration_only_on_supplies_in_file():
    from clinic.schemas import EntityType, GstSupply, TaxProfile

    bare = TaxProfile(entity_type=EntityType.llc, gst_supplies=[GstSupply(country="AU", registered=True)])
    findings, _ = evaluate(bare)
    docket = run_agency(bare, findings)
    assert not any("Australia GST" in w.name for w in docket.worksheet)

    priced = TaxProfile(
        entity_type=EntityType.llc,
        gst_supplies=[GstSupply(country="AU", registered=True, taxable_supplies_usd="100000")],
    )
    findings2, _ = evaluate(priced)
    docket2 = run_agency(priced, findings2)
    gst = next(w for w in docket2.worksheet if "Australia GST" in w.name)
    assert "10,000.00" in gst.result
    assert "not a tax due" in gst.note.lower()

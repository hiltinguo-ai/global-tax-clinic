from clinic.engine import evaluate
from clinic.explain import explain, number_firewall
from clinic.extract import extract
from clinic.personas import PERSONA_TRANSCRIPTS, profile_chen, profile_luis, profile_mei, profile_nori, profile_sichuan


def fired(profile):
    findings, metas = evaluate(profile)
    return {f.rule_id for f in findings}, findings, metas


def test_mei_core_findings():
    ids, findings, _ = fired(profile_mei())
    assert "us.fed.fbar" in ids
    assert "us.fed.3520" in ids
    assert "us.fed.8621" in ids
    assert "us.fed.1116" in ids
    assert "us.fed.8938" in ids
    assert "cn.sta.property" in ids
    assert "xb.fbar_pfic" in ids
    fbar = next(f for f in findings if f.rule_id == "us.fed.fbar")
    assert "15,000.00" in fbar.reason or "15000" in fbar.reason.replace(",", "")


def test_luis_core_findings():
    ids, _, _ = fired(profile_luis())
    assert "us.fed.schedule_c" in ids
    assert "us.fed.se_tax" in ids
    assert "us.fed.tips" in ids
    assert "us.fed.family_credits" in ids
    assert "ma.dor.part_year" in ids
    assert "us.fed.fbar" not in ids


def test_sichuan_core_findings():
    ids, _, _ = fired(profile_sichuan())
    assert "ma.dor.meals" in ids
    assert "ma.dor.sales" in ids
    assert "ma.dor.withholding" in ids
    assert "ma.dor.excise" in ids
    assert "ma.dor.property" in ids
    assert "ma.dor.alcohol" in ids
    assert "xb.meals_alcohol" in ids
    assert "us.fed.ttb_wine" not in ids


def test_nori_core_findings():
    ids, _, _ = fired(profile_nori())
    assert "us.fed.5471" in ids
    assert "us.fed.5472" in ids
    assert "us.fed.83b" in ids
    assert "xb.us_cn_entity" in ids


def test_chen_core_findings():
    profile = profile_chen()
    assert profile.residencies == ["US", "HK"]
    assert float(profile.foreign_account_total()) == 2_000_000
    assert float(profile.public_stakes[0].ownership_pct) == 8
    assert profile.public_stakes[0].years_held == 20
    ids, findings, _ = fired(profile)
    assert "us.fed.fbar" in ids
    assert "us.fed.1041" in ids
    assert "us.fed.founder_public" in ids
    assert "us.fed.grantor_trust" in ids
    assert "us.fed.niit" in ids
    assert "us.fed.1202" in ids
    assert "hk.ird.property_tax" not in ids
    fbar = next(f for f in findings if f.rule_id == "us.fed.fbar")
    assert fbar.status.value == "required"
    assert "2,000,000" in fbar.reason or "2000000" in fbar.reason.replace(",", "")


def test_extractor_matches_persona_transcripts():
    for key, meta in PERSONA_TRANSCRIPTS.items():
        profile, source = extract(meta["text_en"], persona_id=key)
        assert source.startswith("persona:")
        assert profile.display_name or profile.entity_type


def test_number_firewall_strips_invented_amounts():
    _, findings, metas = fired(profile_mei())
    dirty = "You owe $999999 on Form 9999 and maybe 1234567 more."
    clean = number_firewall(dirty, findings)
    assert "999999" not in clean
    assert "1234567" not in clean
    report = explain(profile_mei(), findings, metas)
    assert "not advice" in report.disclaimer.lower()
    assert report.packs_applied

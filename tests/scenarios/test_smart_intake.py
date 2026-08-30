"""Smartness upgrades: negation, tri-valued triggers, amount parsing, questions."""

from clinic.engine import evaluate_detailed
from clinic.extract import extract
from clinic.schemas import FindingStatus
from clinic.visit import run_visit


def test_negation_no_foreign_accounts_settles_fbar():
    profile, _ = extract("I am a US person in Massachusetts. No foreign accounts. No gifts.")
    assert "foreign_accounts" in profile.facts_provided
    assert "gifts" in profile.facts_provided
    findings, _, questions = evaluate_detailed(profile, pack_ids=["us-federal"])
    assert not any(f.rule_id == "us.fed.fbar" for f in findings)
    assert not any(q.field == "foreign_accounts" for q in questions)


def test_account_without_balance_becomes_question_not_silence():
    profile, _ = extract("I'm a US citizen with a Hong Kong bank account at HSBC.")
    assert profile.foreign_accounts  # the account is seen
    assert "foreign_accounts" not in profile.facts_provided  # but balance unknown
    findings, _, questions = evaluate_detailed(profile, pack_ids=["us-federal"])
    fbar = next(f for f in findings if f.rule_id == "us.fed.fbar")
    assert fbar.status == FindingStatus.check
    assert fbar.confidence == "needs_facts"
    assert any(q.field == "foreign_accounts" for q in questions)


def test_chinese_wan_amounts_parse():
    profile, _ = extract("我是美国税务居民。今年父母从国内赠与了我18万美元。")
    assert profile.gifts and float(profile.gifts[0].amount_usd) == 180000
    findings, _, _ = evaluate_detailed(profile, pack_ids=["us-federal"])
    f3520 = next(f for f in findings if f.rule_id == "us.fed.3520")
    assert f3520.status == FindingStatus.required


def test_k_suffix_and_dollar_amounts():
    profile, _ = extract(
        "US person. Foreign accounts: an HSBC account with a max of $8k and a brokerage at $4,500."
    )
    total = float(profile.foreign_account_total())
    assert total == 12500
    findings, _, _ = evaluate_detailed(profile, pack_ids=["us-federal"])
    assert any(f.rule_id == "us.fed.fbar" and f.status == FindingStatus.required for f in findings)


def test_fired_finding_carries_matched_facts():
    profile, _ = extract(
        "I am a US person. HSBC bank account in Hong Kong, max balance 9,000 USD, "
        "and a Hang Seng account with 6,000 USD."
    )
    findings, _, _ = evaluate_detailed(profile, pack_ids=["us-federal"])
    fbar = next(f for f in findings if f.rule_id == "us.fed.fbar")
    assert fbar.status == FindingStatus.required
    assert any("15,000" in m for m in fbar.matched)  # real aggregate, real threshold story


def test_gold_personas_have_no_open_questions():
    out = run_visit(text="", persona_id="mei", jurisdictions=["us-federal", "hong-kong", "cross-border"])
    assert out.questions == []
    assert all(f.confidence == "confirmed" for f in out.findings)


def test_report_lede_describes_the_client_not_just_counts():
    out = run_visit(
        text="I am a US person. My parents in China gifted me $150,000. No foreign accounts.",
        jurisdictions=["us-federal"],
    )
    assert "$150,000" in out.report.lede
    assert "foreign gifts" in out.report.lede


def test_direct_profiles_keep_classic_behavior():
    # legacy pack tests build TaxProfile directly: no facts_provided -> no questions
    from clinic.schemas import TaxProfile

    findings, _, questions = evaluate_detailed(TaxProfile(us_person=True))
    assert questions == []
    assert all(f.confidence == "confirmed" for f in findings)

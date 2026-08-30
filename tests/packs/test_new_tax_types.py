"""Must / must-not trigger tests for the comprehensive-coverage rules
(payroll, baselines, investment-income, corporate estimates, DE franchise,
MA UI/PFML/use tax, CN rental IIT)."""

from clinic.engine import evaluate
from clinic.schemas import (
    EntityType,
    IncomeBand,
    IncomeStream,
    OwnershipLink,
    PublicCompanyStake,
    StateRevenue,
    TaxProfile,
)


def ids(profile: TaxProfile) -> set[str]:
    findings, _ = evaluate(profile)
    return {f.rule_id for f in findings}


def test_1040_must_and_must_not():
    yes = TaxProfile(us_person=True, income_streams=[IncomeStream(kind="w2")])
    no_income = TaxProfile(us_person=True)
    non_us = TaxProfile(us_person=False, income_streams=[IncomeStream(kind="w2")])
    assert "us.fed.1040" in ids(yes)
    assert "us.fed.1040" not in ids(no_income)
    assert "us.fed.1040" not in ids(non_us)


def test_federal_payroll_must_and_must_not():
    yes = TaxProfile(entity_type=EntityType.llc, has_employees=True)
    no = TaxProfile(entity_type=EntityType.llc, has_employees=False)
    indiv = TaxProfile(entity_type=EntityType.individual, has_employees=True)
    assert "us.fed.941" in ids(yes)
    assert "us.fed.941" not in ids(no)
    assert "us.fed.941" not in ids(indiv)  # applies_to gates individuals out


def test_1099_issuer_check_for_operating_entities_only():
    yes = TaxProfile(entity_type=EntityType.c_corp, income_streams=[IncomeStream(kind="sales")])
    no = TaxProfile(entity_type=EntityType.c_corp)
    assert "us.fed.1099_issuer" in ids(yes)
    assert "us.fed.1099_issuer" not in ids(no)


def test_niit_hnw_and_trust_but_not_middle_income():
    hnw = TaxProfile(us_person=True, income_band=IncomeBand.hnw,
                     income_streams=[IncomeStream(kind="rental", country="CN")])
    trust = TaxProfile(us_person=True, entity_type=EntityType.family_trust,
                       public_stakes=[PublicCompanyStake(ownership_pct="8", years_held=20)])
    middle = TaxProfile(us_person=True, income_band=IncomeBand.middle,
                        income_streams=[IncomeStream(kind="rental")])
    assert "us.fed.niit" in ids(hnw)
    assert "us.fed.niit" in ids(trust)
    assert "us.fed.niit" not in ids(middle)


def test_addl_medicare_hnw_wages_only():
    yes = TaxProfile(us_person=True, income_band=IncomeBand.hnw,
                     income_streams=[IncomeStream(kind="w2")])
    low = TaxProfile(us_person=True, income_band=IncomeBand.low_income,
                     income_streams=[IncomeStream(kind="w2")])
    assert "us.fed.addl_medicare" in ids(yes)
    assert "us.fed.addl_medicare" not in ids(low)


def test_form_926_needs_a_foreign_entity():
    yes = TaxProfile(us_person=True, entity_type=EntityType.c_corp,
                     ownerships=[OwnershipLink(name="Shanghai sub", country="CN", ownership_pct="100")])
    us_only = TaxProfile(us_person=True, entity_type=EntityType.c_corp,
                         ownerships=[OwnershipLink(name="US sub", country="US", ownership_pct="100")])
    assert "us.fed.926" in ids(yes)
    assert "us.fed.926" not in ids(us_only)


def test_corporate_estimated_needs_revenue():
    yes = TaxProfile(entity_type=EntityType.c_corp,
                     revenue_by_state=[StateRevenue(state="MA", amount_usd="420000")])
    no = TaxProfile(entity_type=EntityType.c_corp)
    assert "us.fed.1120es" in ids(yes)
    assert "us.fed.1120es" not in ids(no)


def test_de_franchise_incorporation_only():
    yes = TaxProfile(entity_type=EntityType.c_corp, incorporation_state="DE")
    ma_inc = TaxProfile(entity_type=EntityType.c_corp, incorporation_state="MA")
    de_llc = TaxProfile(entity_type=EntityType.llc, incorporation_state="DE")
    assert "de.sos.franchise" in ids(yes)
    assert "de.sos.franchise" not in ids(ma_inc)
    assert "de.sos.franchise" not in ids(de_llc)  # scoped to corporations for now


def test_ma_form1_resident_with_income():
    yes = TaxProfile(us_person=True, states=["MA"], income_streams=[IncomeStream(kind="w2")])
    no_ma = TaxProfile(us_person=True, states=["NH"], income_streams=[IncomeStream(kind="w2")])
    assert "ma.dor.form1" in ids(yes)
    assert "ma.dor.form1" not in ids(no_ma)


def test_ma_ui_and_pfml_employers_only():
    yes = TaxProfile(entity_type=EntityType.llc, has_employees=True, states=["MA"])
    no_employees = TaxProfile(entity_type=EntityType.llc, has_employees=False, states=["MA"])
    out_of_state = TaxProfile(entity_type=EntityType.llc, has_employees=True, states=["NY"])
    got = ids(yes)
    assert "ma.dua.ui" in got and "ma.dfml.pfml" in got
    got_no = ids(no_employees)
    assert "ma.dua.ui" not in got_no and "ma.dfml.pfml" not in got_no
    got_out = ids(out_of_state)
    assert "ma.dua.ui" not in got_out and "ma.dfml.pfml" not in got_out


def test_ma_use_tax_is_a_low_check():
    findings, _ = evaluate(TaxProfile(us_person=True, states=["MA"]))
    f = next(x for x in findings if x.rule_id == "ma.dor.use_tax")
    assert f.status.value == "check" and f.severity.value == "low"
    assert "ma.dor.use_tax" not in ids(TaxProfile(us_person=True, states=["CA"]))


def test_cn_rental_iit_must_and_must_not():
    yes = TaxProfile(us_person=True, income_streams=[IncomeStream(kind="rental", country="CN")])
    us_rental = TaxProfile(us_person=True, income_streams=[IncomeStream(kind="rental", country="US")])
    assert "cn.sta.iit_rental" in ids(yes)
    assert "cn.sta.iit_rental" not in ids(us_rental)

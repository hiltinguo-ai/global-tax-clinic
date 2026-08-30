"""Must / must-not tests for the HK + CN mainland coverage pass
(MPF, business registration, VAT surcharges, stamp duty, cross-border WHT,
social insurance)."""

from clinic.engine import evaluate
from clinic.schemas import EntityType, GstSupply, OwnershipLink, TaxProfile


def ids(profile: TaxProfile) -> set[str]:
    findings, _ = evaluate(profile)
    return {f.rule_id for f in findings}


def test_hk_mpf_employer_must_and_must_not():
    yes = TaxProfile(entity_type=EntityType.llc, has_employees=True, residencies=["HK"])
    no_hk = TaxProfile(entity_type=EntityType.llc, has_employees=True, residencies=["US"])
    no_emp = TaxProfile(entity_type=EntityType.llc, has_employees=False, residencies=["HK"])
    indiv = TaxProfile(entity_type=EntityType.individual, has_employees=True, residencies=["HK"])
    assert "hk.mpfa.mpf" in ids(yes)
    assert "hk.mpfa.mpf" not in ids(no_hk)
    assert "hk.mpfa.mpf" not in ids(no_emp)
    assert "hk.mpfa.mpf" not in ids(indiv)


def test_hk_business_registration_entities_in_hk_only():
    yes = TaxProfile(entity_type=EntityType.c_corp, residencies=["HK"])
    us_corp = TaxProfile(entity_type=EntityType.c_corp, residencies=["US"])
    hk_individual = TaxProfile(entity_type=EntityType.individual, residencies=["HK"])
    assert "hk.ird.br" in ids(yes)
    assert "hk.ird.br" not in ids(us_corp)
    assert "hk.ird.br" not in ids(hk_individual)


def test_cn_vat_surtaxes_ride_on_vat():
    yes = TaxProfile(entity_type=EntityType.llc,
                     gst_supplies=[GstSupply(country="CN", amount_usd="50000")])
    no = TaxProfile(entity_type=EntityType.llc)
    assert "cn.sta.surtaxes" in ids(yes)
    assert "cn.sta.surtaxes" not in ids(no)


def test_cn_stamp_duty_needs_a_mainland_footprint():
    via_sub = TaxProfile(entity_type=EntityType.c_corp,
                         ownerships=[OwnershipLink(name="Shanghai sub", country="CN", ownership_pct="100")])
    no_cn = TaxProfile(entity_type=EntityType.c_corp,
                       ownerships=[OwnershipLink(name="US sub", country="US", ownership_pct="100")])
    assert "cn.sta.stamp_duty" in ids(via_sub)
    assert "cn.sta.stamp_duty" not in ids(no_cn)


def test_cn_wht_and_social_insurance_for_cn_sub_owners():
    yes = TaxProfile(entity_type=EntityType.c_corp,
                     ownerships=[OwnershipLink(name="Shanghai sub", country="CN", ownership_pct="100")])
    got = ids(yes)
    assert "cn.sta.wht" in got
    assert "cn.hrss.social" in got
    no = TaxProfile(entity_type=EntityType.c_corp)
    got_no = ids(no)
    assert "cn.sta.wht" not in got_no
    assert "cn.hrss.social" not in got_no
    indiv = TaxProfile(entity_type=EntityType.individual,
                       ownerships=[OwnershipLink(name="Shanghai sub", country="CN", ownership_pct="100")])
    assert "cn.hrss.social" not in ids(indiv)  # entity-side obligation

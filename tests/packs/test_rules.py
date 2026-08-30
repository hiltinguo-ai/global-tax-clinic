from clinic.engine import evaluate
from clinic.schemas import (
    AlcoholLine,
    EntityType,
    GstSupply,
    IncomeBand,
    RealProperty,
    ForeignAccount,
    Gift,
    IncomeStream,
    LifeEvent,
    OwnershipLink,
    PublicCompanyStake,
    StateRevenue,
    TaxProfile,
)


def ids(profile: TaxProfile) -> set[str]:
    findings, _ = evaluate(profile)
    return {f.rule_id for f in findings}


def test_fbar_must_and_must_not():
    yes = TaxProfile(
        us_person=True,
        foreign_accounts=[
            ForeignAccount(country="HK", max_balance_usd="3000"),
            ForeignAccount(country="HK", max_balance_usd="3000"),
            ForeignAccount(country="HK", max_balance_usd="3000"),
            ForeignAccount(country="HK", max_balance_usd="3000"),
        ],
    )
    no = TaxProfile(
        us_person=True,
        foreign_accounts=[ForeignAccount(country="HK", max_balance_usd="3000")],
    )
    assert "us.fed.fbar" in ids(yes)
    assert "us.fed.fbar" not in ids(no)


def test_3520_threshold():
    yes = TaxProfile(us_person=True, gifts=[Gift(source_country="CN", amount_usd="180000")])
    no = TaxProfile(us_person=True, gifts=[Gift(source_country="CN", amount_usd="80000")])
    assert "us.fed.3520" in ids(yes)
    assert "us.fed.3520" not in ids(no)


def test_pfic_fund_kind():
    yes = TaxProfile(us_person=True, foreign_accounts=[ForeignAccount(country="HK", kind="fund")])
    no = TaxProfile(us_person=True, foreign_accounts=[ForeignAccount(country="HK", kind="bank")])
    assert "us.fed.8621" in ids(yes)
    assert "us.fed.8621" not in ids(no)


def test_schedule_c_and_not_on_w2_only():
    yes = TaxProfile(us_person=True, income_streams=[IncomeStream(kind="1099_nec")])
    no = TaxProfile(us_person=True, income_streams=[IncomeStream(kind="w2")])
    assert "us.fed.schedule_c" in ids(yes)
    assert "us.fed.schedule_c" not in ids(no)


def test_ma_part_year():
    yes = TaxProfile(us_person=True, part_year_states=["MA"])
    no = TaxProfile(us_person=True, states=["NH"])
    assert "ma.dor.part_year" in ids(yes)
    assert "ma.dor.part_year" not in ids(no)


def test_ma_meals_restaurant_only():
    yes = TaxProfile(entity_type=EntityType.llc, states=["MA"], has_restaurant=True, us_person=True)
    no = TaxProfile(entity_type=EntityType.llc, states=["MA"], has_restaurant=False, us_person=True)
    assert "ma.dor.meals" in ids(yes)
    assert "ma.dor.meals" not in ids(no)


def test_5471_and_5472_entity():
    nori = TaxProfile(
        entity_type=EntityType.c_corp,
        us_person=True,
        chinese_founders=True,
        ownerships=[OwnershipLink(name="Shanghai", country="CN", ownership_pct="100")],
        life_events=[LifeEvent(kind="equity_grant")],
        states=["DE", "MA"],
    )
    fired = ids(nori)
    assert "us.fed.5471" in fired
    assert "us.fed.5472" in fired
    assert "us.fed.83b" in fired
    assert "xb.us_cn_entity" in fired


def test_saas_sales_must_and_must_not():
    yes = TaxProfile(
        entity_type=EntityType.c_corp,
        industry="saas",
        states=["MA"],
        us_person=True,
        revenue_by_state=[StateRevenue(state="MA", amount_usd="420000")],
    )
    no = TaxProfile(
        entity_type=EntityType.c_corp,
        industry="robotics",
        states=["MA"],
        us_person=True,
    )
    assert "ma.dor.saas_sales" in ids(yes)
    assert "ma.dor.saas_sales" not in ids(no)


def test_out_of_state_revenue_is_review():
    yes = TaxProfile(
        entity_type=EntityType.c_corp,
        states=["MA"],
        us_person=True,
        revenue_by_state=[
            StateRevenue(state="MA", amount_usd="100"),
            StateRevenue(state="NY", amount_usd="240000"),
        ],
    )
    no = TaxProfile(entity_type=EntityType.c_corp, states=["MA"], us_person=True)
    assert "us.state.economic_nexus_review" in ids(yes)
    assert "us.state.economic_nexus_review" not in ids(no)


def test_hk_salaries_needs_hk_fact():
    yes = TaxProfile(us_person=True, residencies=["HK"])
    no = TaxProfile(us_person=True, residencies=["US"])
    assert "hk.ird.salaries" in ids(yes)
    assert "hk.ird.salaries" not in ids(no)


def test_china_183_and_ties():
    resident = TaxProfile(us_person=True, residencies=["CN"], days_in_cn=200)
    visitor = TaxProfile(us_person=True, residencies=["CN"], days_in_cn=40)
    neither = TaxProfile(us_person=True, residencies=["US"])
    assert "cn.sta.iit_183" in ids(resident)
    assert "cn.sta.iit_183" not in ids(visitor)
    assert "cn.sta.iit_ties" in ids(visitor)
    assert "cn.sta.iit_ties" not in ids(neither)


def test_family_trust_and_founder_listed_stake():
    trust = TaxProfile(
        entity_type=EntityType.family_trust,
        us_person=True,
        public_stakes=[
            PublicCompanyStake(
                name="Northline",
                country="US",
                listed=True,
                ownership_pct="8",
                years_held=20,
                founded_by_client=True,
            )
        ],
    )
    person = TaxProfile(
        entity_type=EntityType.individual,
        us_person=True,
        public_stakes=[
            PublicCompanyStake(
                name="Northline",
                country="US",
                listed=True,
                ownership_pct="8",
                years_held=20,
                founded_by_client=True,
            )
        ],
    )
    none = TaxProfile(entity_type=EntityType.individual, us_person=True)
    fired_trust = ids(trust)
    fired_person = ids(person)
    assert "us.fed.1041" in fired_trust
    assert "us.fed.grantor_trust" in fired_trust
    assert "us.fed.founder_public" in fired_trust
    assert "us.fed.1202" in fired_trust
    assert "us.fed.1041" not in fired_person
    assert "us.fed.founder_public" in fired_person
    assert "us.fed.founder_public" not in ids(none)


def test_hnw_individual_and_family_trust_both_on_file():
    both = TaxProfile(
        entity_type=EntityType.individual,
        income_band=IncomeBand.hnw,
        has_family_trust=True,
        us_person=True,
    )
    person_only = TaxProfile(
        entity_type=EntityType.individual,
        income_band=IncomeBand.hnw,
        us_person=True,
    )
    fired = ids(both)
    assert both.types_on_file() == ["individual", "family_trust"]
    assert "us.fed.1041" in fired
    assert "us.fed.grantor_trust" in fired
    assert "us.fed.709" in fired
    assert "us.fed.1041" not in ids(person_only)


def test_property_alcohol_and_gst_must_and_must_not():
    ma_prop = TaxProfile(
        entity_type=EntityType.individual,
        us_person=True,
        states=["MA"],
        properties=[RealProperty(country="US", state="MA", kind="residential")],
    )
    no_prop = TaxProfile(entity_type=EntityType.individual, us_person=True, states=["MA"])
    assert "ma.dor.property" in ids(ma_prop)
    assert "us.fed.property_local" in ids(ma_prop)
    assert "ma.dor.property" not in ids(no_prop)

    winery = TaxProfile(
        entity_type=EntityType.llc,
        us_person=True,
        states=["MA"],
        alcohol=[AlcoholLine(country="US", state="MA", kind="wine", role="producer", licensed=True)],
    )
    restaurant_wine = TaxProfile(
        entity_type=EntityType.llc,
        us_person=True,
        states=["MA"],
        has_restaurant=True,
        alcohol=[AlcoholLine(country="US", state="MA", kind="wine", role="restaurant", licensed=True)],
    )
    dry = TaxProfile(entity_type=EntityType.llc, us_person=True, states=["MA"], has_restaurant=True)
    assert "us.fed.ttb_wine" in ids(winery)
    assert "ma.dor.alcohol" in ids(winery)
    assert "us.fed.ttb_wine" not in ids(restaurant_wine)
    assert "ma.dor.alcohol" in ids(restaurant_wine)
    assert "ma.dor.alcohol" not in ids(dry)
    assert "us.fed.ttb_wine" not in ids(dry)

    hk_flat = TaxProfile(
        us_person=True,
        residencies=["US", "HK"],
        properties=[RealProperty(country="HK", kind="rental", rental=True)],
    )
    assert "hk.ird.property_tax" in ids(hk_flat)
    assert "hk.rvd.rates" in ids(hk_flat)
    assert "hk.ird.property_tax" not in ids(no_prop)

    au = TaxProfile(entity_type=EntityType.llc, gst_supplies=[GstSupply(country="AU", registered=True)])
    sg = TaxProfile(entity_type=EntityType.llc, gst_supplies=[GstSupply(country="SG")])
    ca = TaxProfile(entity_type=EntityType.llc, gst_supplies=[GstSupply(country="CA")])
    uk = TaxProfile(entity_type=EntityType.llc, gst_supplies=[GstSupply(country="UK")])
    cn_vat = TaxProfile(entity_type=EntityType.llc, gst_supplies=[GstSupply(country="CN")])
    none_gst = TaxProfile(entity_type=EntityType.llc)
    assert "au.ato.gst" in ids(au)
    assert "sg.iras.gst" in ids(sg)
    assert "ca.cra.gst_hst" in ids(ca)
    assert "uk.hmrc.vat" in ids(uk)
    assert "cn.sta.vat" in ids(cn_vat)
    assert "au.ato.gst" not in ids(none_gst)
    assert "sg.iras.gst" not in ids(none_gst)

    brewery = TaxProfile(
        entity_type=EntityType.llc,
        us_person=True,
        alcohol=[AlcoholLine(country="US", kind="beer", role="producer")],
    )
    distillery = TaxProfile(
        entity_type=EntityType.llc,
        us_person=True,
        alcohol=[AlcoholLine(country="US", kind="spirits", role="importer")],
    )
    pub = TaxProfile(
        entity_type=EntityType.llc,
        us_person=True,
        has_restaurant=True,
        alcohol=[AlcoholLine(country="US", kind="beer", role="restaurant")],
    )
    assert "us.fed.ttb_beer" in ids(brewery)
    assert "us.fed.ttb_spirits" in ids(distillery)
    assert "us.fed.ttb_beer" not in ids(pub)
    assert "us.fed.ttb_spirits" not in ids(pub)
    assert "us.fed.ttb_wine" not in ids(brewery)

    au_wine = TaxProfile(
        entity_type=EntityType.llc,
        residencies=["AU"],
        alcohol=[AlcoholLine(country="AU", kind="wine", role="wholesale")],
        properties=[RealProperty(country="AU")],
    )
    assert "au.ato.wet" in ids(au_wine)
    assert "au.ato.land_tax" in ids(au_wine)
    assert "au.ato.wet" not in ids(dry)

    sg_flat = TaxProfile(us_person=True, properties=[RealProperty(country="SG")])
    uk_shop = TaxProfile(
        residencies=["UK"],
        properties=[RealProperty(country="UK", kind="commercial")],
        alcohol=[AlcoholLine(country="UK", kind="wine", role="retail")],
    )
    ca_file = TaxProfile(
        residencies=["CA"],
        properties=[RealProperty(country="CA")],
        alcohol=[AlcoholLine(country="CA", kind="wine", role="producer")],
    )
    cn_baijiu = TaxProfile(
        residencies=["CN"],
        alcohol=[AlcoholLine(country="CN", kind="spirits", role="producer")],
        properties=[RealProperty(country="CN")],
    )
    assert "sg.iras.property" in ids(sg_flat)
    assert "sg.iras.property" not in ids(no_prop)
    assert "uk.voa.rates" in ids(uk_shop)
    assert "uk.hmrc.alcohol" in ids(uk_shop)
    assert "uk.voa.rates" not in ids(no_prop)
    assert "ca.prov.property" in ids(ca_file)
    assert "ca.cra.alcohol" in ids(ca_file)
    assert "cn.sta.excise_alcohol" in ids(cn_baijiu)
    assert "cn.sta.property" in ids(cn_baijiu)
    assert "hk.ird.stamp_duty" in ids(hk_flat)
    assert "hk.ird.stamp_duty" not in ids(no_prop)
    assert "hk.ced.liquor" not in ids(hk_flat)


def test_europe_vat_needs_eu_residency():
    yes = TaxProfile(us_person=True, residencies=["EU"])
    no = TaxProfile(us_person=True, residencies=["US"])
    assert "eu.vat.oss" in ids(yes)
    assert "eu.vat.oss" not in ids(no)

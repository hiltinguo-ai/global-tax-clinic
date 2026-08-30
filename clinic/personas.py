from __future__ import annotations

from clinic.schemas import (
    AlcoholLine,
    EntityType,
    ForeignAccount,
    Gift,
    IncomeBand,
    IncomeStream,
    LifeEvent,
    OwnershipLink,
    PublicCompanyStake,
    RealProperty,
    StateRevenue,
    TaxProfile,
)

PERSONA_TRANSCRIPTS: dict[str, dict] = {
    "mei": {
        "id": "mei",
        "tag": "Individual · HNW",
        "name": "Mei",
        "locale": "zh",
        "blurb": "US resident with HK and mainland ties",
        "entity_type": "individual",
        "income_band": "hnw",
        "jurisdictions": ["us-federal", "hong-kong", "china-mainland", "cross-border"],
        "text_en": (
            "I am a US resident and US person. I have five Hong Kong accounts: "
            "HSBC bank 3,200 USD, Hang Seng 2,800, a brokerage 4,100, an MPF of 1,400, "
            "and a Hong Kong retail equity fund with a peak of 3,500. "
            "I rent out a Shenzhen apartment. I have RSUs from my US employer. "
            "My parents in China gifted me 180,000 USD this year."
        ),
        "text_zh": (
            "我是美国税务居民。我在香港有五个账户：汇丰银行存款约3200美元，恒生2800，"
            "券商账户4100，强积金1400，还有一个香港零售基金，年内最高约3500美元。"
            "深圳有一套公寓在出租。美国雇主给了RSU。今年父母从国内赠与了我18万美元。"
        ),
    },
    "luis": {
        "id": "luis",
        "tag": "Individual · Working class",
        "name": "Luis",
        "locale": "en",
        "blurb": "W-2 server with DoorDash on the side",
        "entity_type": "individual",
        "income_band": "low_income",
        "jurisdictions": ["us-federal", "massachusetts"],
        "text_en": (
            "I am a US person. I wait tables in Massachusetts on a W-2 and get cash tips. "
            "I also DoorDash on a 1099-NEC. I moved from MA to New Hampshire in July. "
            "I have one child. No foreign accounts."
        ),
        "text_zh": "",
    },
    "sichuan": {
        "id": "sichuan",
        "tag": "Entity · Restaurant LLC",
        "name": "Sichuan Garden LLC",
        "locale": "en",
        "blurb": "Massachusetts restaurant, sales and meals tax",
        "entity_type": "llc",
        "income_band": "",
        "jurisdictions": ["us-federal", "massachusetts"],
        "text_en": (
            "Sichuan Garden is a Massachusetts single-member LLC restaurant. "
            "We serve meals, sell some retail merch, and have employees. "
            "We hold a Brookline commercial property and an ABCC pouring license; "
            "wine by the glass is on the POS. "
            "The owner is a US person. No foreign subsidiary."
        ),
        "text_zh": "",
    },
    "nimbus": {
        "id": "nimbus",
        "tag": "Entity · SaaS C-corp",
        "name": "NimbusFlow, Inc.",
        "locale": "en",
        "blurb": "MA C-corp SaaS — counsel, accountant, compliance",
        "entity_type": "c_corp",
        "income_band": "",
        "jurisdictions": ["us-federal", "massachusetts", "other-us-states"],
        "text_en": (
            "NimbusFlow, Inc. is a Massachusetts C-corporation, incorporated 15 March 2023, "
            "SaaS (NAICS 513210), HQ at 12 Winter St, Boston. Three employees all work in MA, "
            "payroll 490,000. 2025 revenue by billing state: MA 420,000 (taxable SaaS), "
            "NY 240,000, CA 180,000, TX 120,000 (SaaS exempt), IL 90,000, other 200,000. "
            "Total revenue 1,250,000. US person. No foreign accounts."
        ),
        "text_zh": "",
    },
    "nori": {
        "id": "nori",
        "tag": "Entity · C-corp",
        "name": "Nori Robotics Inc.",
        "locale": "en",
        "blurb": "Delaware C-corp, Chinese founders, Shanghai sub",
        "entity_type": "c_corp",
        "income_band": "",
        "jurisdictions": ["us-federal", "massachusetts", "cross-border"],
        "text_en": (
            "Nori Robotics Inc. is a Delaware C-corporation with operations in Massachusetts. "
            "The founders are Chinese and own more than 25 percent. "
            "There is a Shanghai subsidiary. We just granted unvested founder stock. "
            "The company is a US person."
        ),
        "text_zh": "",
    },
    "chen": {
        "id": "chen",
        "tag": "Family trust · founder",
        "name": "Chen Family Trust",
        "locale": "en",
        "blurb": "Trust holds 8% of a US listed company the settlor founded 20 years ago",
        "entity_type": "family_trust",
        "income_band": "hnw",
        "jurisdictions": ["us-federal", "massachusetts"],
        "text_en": (
            "The Chen Family Trust is a US family trust. The settlor founded Northline Inc., "
            "took it public about 20 years ago, and the trust still owns 8 percent of the listed shares. "
            "US person. Massachusetts situs. Dividends are paid to the trust each year."
        ),
        "text_zh": "",
    },
}


def profile_mei() -> TaxProfile:
    return TaxProfile(
        tax_year=2026,
        entity_type=EntityType.individual,
        display_name="Mei",
        income_band=IncomeBand.hnw,
        us_person=True,
        residencies=["US", "HK"],
        states=["CA"],
        days_in_cn=40,
        filing_status="single",
        foreign_accounts=[
            ForeignAccount(country="HK", label="HSBC", kind="bank", max_balance_usd="3200"),
            ForeignAccount(country="HK", label="Hang Seng", kind="bank", max_balance_usd="2800"),
            ForeignAccount(country="HK", label="HK brokerage", kind="brokerage", max_balance_usd="4100"),
            ForeignAccount(country="HK", label="MPF", kind="mpf", max_balance_usd="1400"),
            ForeignAccount(country="HK", label="HK retail fund", kind="fund", max_balance_usd="3500"),
        ],
        income_streams=[
            IncomeStream(kind="rsu", country="US", amount_usd="0", employer="US employer"),
            IncomeStream(kind="rental", country="CN", amount_usd="18000", notes="Shenzhen apartment"),
        ],
        gifts=[Gift(from_foreign_person=True, source_country="CN", amount_usd="180000", year=2026)],
        properties=[
            RealProperty(country="CN", locality="Shenzhen", kind="rental", rental=True),
        ],
        notes="Parents gifted cash from mainland China. HK funds may be PFICs.",
    )


def profile_luis() -> TaxProfile:
    return TaxProfile(
        tax_year=2026,
        entity_type=EntityType.individual,
        display_name="Luis",
        income_band=IncomeBand.low_income,
        us_person=True,
        residencies=["US"],
        states=["MA", "NH"],
        part_year_states=["MA", "NH"],
        filing_status="hoh",
        dependents=1,
        income_streams=[
            IncomeStream(kind="w2", country="US", state="MA", amount_usd="32000", employer="restaurant"),
            IncomeStream(kind="tips", country="US", state="MA", amount_usd="14000"),
            IncomeStream(kind="1099_nec", country="US", state="MA", amount_usd="9000", employer="DoorDash"),
        ],
        life_events=[LifeEvent(kind="move_state", from_state="MA", to_state="NH", date="2026-07-15")],
    )


def profile_sichuan() -> TaxProfile:
    return TaxProfile(
        tax_year=2026,
        entity_type=EntityType.llc,
        display_name="Sichuan Garden LLC",
        us_person=True,
        residencies=["US"],
        states=["MA"],
        has_restaurant=True,
        has_employees=True,
        income_streams=[
            IncomeStream(kind="sales", country="US", state="MA", amount_usd="420000", notes="meals + merch"),
        ],
        industry="restaurant",
        incorporation_state="MA",
        properties=[
            RealProperty(country="US", state="MA", locality="Brookline", kind="commercial"),
        ],
        alcohol=[
            AlcoholLine(country="US", state="MA", kind="wine", role="restaurant", licensed=True, sales_usd="48000"),
        ],
        notes="Massachusetts single-member LLC restaurant.",
    )


def profile_nimbus() -> TaxProfile:
    return TaxProfile(
        tax_year=2025,
        entity_type=EntityType.c_corp,
        display_name="NimbusFlow, Inc.",
        us_person=True,
        residencies=["US"],
        states=["MA"],
        industry="saas",
        incorporation_state="MA",
        has_employees=True,
        employee_states=["MA"],
        payroll_usd="490000",
        revenue_by_state=[
            StateRevenue(state="MA", amount_usd="420000", customers=14, saas_taxable=True),
            StateRevenue(state="NY", amount_usd="240000", customers=8, saas_taxable=True),
            StateRevenue(state="CA", amount_usd="180000", customers=6, saas_taxable=True),
            StateRevenue(state="TX", amount_usd="120000", customers=5, saas_taxable=False),
            StateRevenue(state="IL", amount_usd="90000", customers=3, saas_taxable=True),
            StateRevenue(state="OTHER", amount_usd="200000", customers=14, saas_taxable=None),
        ],
        income_streams=[
            IncomeStream(kind="saas", country="US", state="MA", amount_usd="420000"),
        ],
        notes="Justin agency sample: MA C-corp SaaS. Out-of-state receipts stay REVIEW.",
    )


def profile_nori() -> TaxProfile:
    return TaxProfile(
        tax_year=2026,
        entity_type=EntityType.c_corp,
        display_name="Nori Robotics Inc.",
        us_person=True,
        residencies=["US"],
        states=["DE", "MA"],
        incorporation_state="DE",
        chinese_founders=True,
        has_employees=True,
        ownerships=[
            OwnershipLink(name="Shanghai subsidiary", country="CN", entity_type="corp", ownership_pct="100", role="parent"),
            OwnershipLink(name="Founder A", country="CN", entity_type="individual", ownership_pct="40", role="founder"),
        ],
        life_events=[LifeEvent(kind="equity_grant", date="2026-08-01", notes="unvested founder stock")],
        notes="Delaware C-corp, MA operations, Chinese founders, Shanghai sub.",
    )


def profile_chen() -> TaxProfile:
    return TaxProfile(
        tax_year=2026,
        entity_type=EntityType.family_trust,
        display_name="Chen Family Trust",
        income_band=IncomeBand.hnw,
        us_person=True,
        residencies=["US"],
        states=["MA"],
        public_stakes=[
            PublicCompanyStake(
                name="Northline Inc.",
                country="US",
                listed=True,
                ownership_pct="8",
                years_held=20,
                founded_by_client=True,
            )
        ],
        income_streams=[IncomeStream(kind="dividends", country="US", amount_usd="0", notes="listed founder stock")],
        notes="Family trust holding 8% of a US listed company the settlor founded 20 years ago.",
    )


PROFILES = {
    "mei": profile_mei,
    "luis": profile_luis,
    "sichuan": profile_sichuan,
    "nimbus": profile_nimbus,
    "nori": profile_nori,
    "chen": profile_chen,
}


def list_personas() -> list[dict]:
    out = []
    for key, meta in PERSONA_TRANSCRIPTS.items():
        out.append({**meta, "id": key})
    return out

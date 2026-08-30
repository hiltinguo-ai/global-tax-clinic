from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator


class EntityType(str, Enum):
    individual = "individual"
    llc = "llc"
    c_corp = "c_corp"
    family_trust = "family_trust"


class IncomeBand(str, Enum):
    hnw = "hnw"
    middle = "middle"
    low_income = "low_income"


class FindingStatus(str, Enum):
    required = "required"
    likely = "likely"
    check = "check"
    na = "n.a."


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Citation(BaseModel):
    src: str
    url: str
    passage_id: str | None = None


class ForeignAccount(BaseModel):
    country: str
    label: str = ""
    kind: str = "bank"  # bank, brokerage, fund, mpf, housing_fund
    max_balance_usd: Decimal = Decimal("0")
    currency: str = "USD"

    @field_validator("max_balance_usd", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal:
        return Decimal(str(v)) if v is not None else Decimal("0")


class IncomeStream(BaseModel):
    kind: str  # w2, tips, 1099_nec, rental, rsu, interest, sales
    country: str = "US"
    state: str | None = None
    amount_usd: Decimal | None = None
    employer: str | None = None
    notes: str | None = None

    @field_validator("amount_usd", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal | None:
        return None if v in (None, "") else Decimal(str(v))


class OwnershipLink(BaseModel):
    name: str
    country: str
    entity_type: str = "corp"
    ownership_pct: Decimal = Decimal("0")
    role: str | None = None  # founder, officer, director, shareholder

    @field_validator("ownership_pct", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal:
        return Decimal(str(v)) if v is not None else Decimal("0")


class Gift(BaseModel):
    from_foreign_person: bool = True
    source_country: str
    amount_usd: Decimal
    year: int = 2026

    @field_validator("amount_usd", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class StateRevenue(BaseModel):
    state: str
    amount_usd: Decimal
    customers: int | None = None
    saas_taxable: bool | None = None

    @field_validator("amount_usd", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class PublicCompanyStake(BaseModel):
    name: str = ""
    country: str = "US"
    listed: bool = True
    ownership_pct: Decimal = Decimal("0")
    years_held: int = 20
    founded_by_client: bool = True

    @field_validator("ownership_pct", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal:
        return Decimal(str(v)) if v is not None else Decimal("0")


class LifeEvent(BaseModel):
    kind: str  # move_state, birth, equity_grant, incorporation
    from_state: str | None = None
    to_state: str | None = None
    date: str | None = None
    notes: str | None = None


class RealProperty(BaseModel):
    country: str = "US"
    state: str | None = None
    locality: str | None = None
    kind: str = "residential"  # residential, commercial, rental
    assessed_value_usd: Decimal | None = None
    rental: bool = False

    @field_validator("assessed_value_usd", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal | None:
        return None if v in (None, "") else Decimal(str(v))


class AlcoholLine(BaseModel):
    country: str = "US"
    state: str | None = None
    kind: str = "wine"  # wine, beer, spirits
    role: str = "retail"  # producer, importer, wholesale, retail, restaurant
    licensed: bool = False
    sales_usd: Decimal | None = None

    @field_validator("sales_usd", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal | None:
        return None if v in (None, "") else Decimal(str(v))


class GstSupply(BaseModel):
    country: str  # AU, SG, CA, UK, EU, CN
    registered: bool | None = None
    taxable_supplies_usd: Decimal | None = None

    @field_validator("taxable_supplies_usd", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal | None:
        return None if v in (None, "") else Decimal(str(v))


class TaxProfile(BaseModel):
    tax_year: int = 2026
    entity_type: EntityType = EntityType.individual
    display_name: str | None = None
    us_person: bool = False
    residencies: list[str] = Field(default_factory=list)  # US, HK, CN, AU, states
    states: list[str] = Field(default_factory=list)
    part_year_states: list[str] = Field(default_factory=list)
    days_in_cn: int | None = None
    filing_status: str | None = None
    dependents: int = 0
    foreign_accounts: list[ForeignAccount] = Field(default_factory=list)
    income_streams: list[IncomeStream] = Field(default_factory=list)
    ownerships: list[OwnershipLink] = Field(default_factory=list)
    gifts: list[Gift] = Field(default_factory=list)
    life_events: list[LifeEvent] = Field(default_factory=list)
    has_restaurant: bool = False
    has_employees: bool = False
    chinese_founders: bool = False
    income_band: IncomeBand | None = None
    # A family trust is often on the same engagement as the HNW settlor / beneficiary.
    # entity_type stays the primary client; this flag puts the trust on the file too.
    has_family_trust: bool = False
    industry: str | None = None  # saas, restaurant, robotics, ...
    incorporation_state: str | None = None
    revenue_by_state: list[StateRevenue] = Field(default_factory=list)
    employee_states: list[str] = Field(default_factory=list)
    payroll_usd: Decimal | None = None
    public_stakes: list[PublicCompanyStake] = Field(default_factory=list)
    properties: list[RealProperty] = Field(default_factory=list)
    alcohol: list[AlcoholLine] = Field(default_factory=list)
    gst_supplies: list[GstSupply] = Field(default_factory=list)
    notes: str | None = None
    # Fields the intake actually established (even as "none"). Empty = legacy
    # profile: every default is treated as a known fact, tri-valued logic off.
    facts_provided: list[str] = Field(default_factory=list)

    @field_validator("payroll_usd", mode="before")
    @classmethod
    def _payroll(cls, v: Any) -> Decimal | None:
        return None if v in (None, "") else Decimal(str(v))

    @model_validator(mode="after")
    def _trust_follows_entity(self) -> "TaxProfile":
        if self.entity_type == EntityType.family_trust:
            self.has_family_trust = True
        return self

    def types_on_file(self) -> list[str]:
        types = [self.entity_type.value]
        if self.has_family_trust and EntityType.family_trust.value not in types:
            types.append(EntityType.family_trust.value)
        return types

    def foreign_account_total(self) -> Decimal:
        return sum((a.max_balance_usd for a in self.foreign_accounts), Decimal("0"))

    def income_of(self, *kinds: str) -> list[IncomeStream]:
        wanted = {k.lower() for k in kinds}
        return [s for s in self.income_streams if s.kind.lower() in wanted]

    def has_income(self, *kinds: str) -> bool:
        return bool(self.income_of(*kinds))

    def has_property(self, *keys: str) -> bool:
        if not keys:
            return bool(self.properties)
        want = {k.upper() for k in keys}
        return any(
            (p.state or "").upper() in want or (p.country or "").upper() in want
            for p in self.properties
        )

    def has_alcohol(self, *kinds: str) -> bool:
        if not kinds:
            return bool(self.alcohol)
        want = {k.lower() for k in kinds}
        return any(a.kind.lower() in want or a.role.lower() in want for a in self.alcohol)

    def alcohol_match(self, kind: str, *roles: str) -> bool:
        """True when one alcohol line has this kind and (if given) one of the roles."""
        k = kind.lower()
        want_roles = {r.lower() for r in roles}
        return any(
            a.kind.lower() == k and (not want_roles or a.role.lower() in want_roles)
            for a in self.alcohol
        )

    def has_gst(self, *countries: str) -> bool:
        if not countries:
            return bool(self.gst_supplies)
        want = {c.upper() for c in countries}
        return any((g.country or "").upper() in want for g in self.gst_supplies)

    def gst_supplies_usd(self, country: str) -> Decimal:
        c = country.upper()
        return sum(
            (g.taxable_supplies_usd or Decimal("0") for g in self.gst_supplies if (g.country or "").upper() == c),
            Decimal("0"),
        )

    def income_total(self, *kinds: str) -> Decimal:
        return sum((s.amount_usd or Decimal("0") for s in self.income_of(*kinds)), Decimal("0"))

    def state_revenue(self, state: str) -> Decimal:
        return sum(
            (row.amount_usd for row in self.revenue_by_state if row.state == state),
            Decimal("0"),
        )

    def total_revenue(self) -> Decimal:
        if self.revenue_by_state:
            return sum((row.amount_usd for row in self.revenue_by_state), Decimal("0"))
        return self.income_total("sales", "saas", "w2", "1099_nec", "tips", "rental")

    @computed_field
    @property
    def out_of_state_revenue_count(self) -> int:
        physical = set(self.states)
        return sum(1 for row in self.revenue_by_state if row.state not in physical)

    @computed_field
    @property
    def has_founder_listed_stake(self) -> bool:
        return any(s.founded_by_client and s.listed for s in self.public_stakes)

    @computed_field
    @property
    def founder_listed_years(self) -> int:
        years = [s.years_held for s in self.public_stakes if s.founded_by_client and s.listed]
        return max(years) if years else 0

    @computed_field
    @property
    def founder_foreign_listed_pct(self) -> Decimal:
        pcts = [
            s.ownership_pct
            for s in self.public_stakes
            if s.listed and s.founded_by_client and s.country not in {"US", "", "USA"}
        ]
        return max(pcts) if pcts else Decimal("0")


class Deadline(BaseModel):
    date: str
    auto_extension_to: str | None = None
    note: str | None = None


class Finding(BaseModel):
    rule_id: str
    name: str
    status: FindingStatus
    severity: Severity
    jurisdiction: str
    pack_id: str
    pack_version: str
    tax_year: str
    reason: str
    evidence_needed: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    explain_hints: list[str] = Field(default_factory=list)
    deadline: Deadline | None = None
    numbers: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    paired_with: list[str] = Field(default_factory=list)
    escalate: bool = False
    confidence: str = "confirmed"  # confirmed | needs_facts
    matched: list[str] = Field(default_factory=list)  # human-readable satisfied conditions
    open_questions: list[str] = Field(default_factory=list)


class OpenQuestion(BaseModel):
    field: str
    question: str
    severity: str = "medium"
    rules: list[str] = Field(default_factory=list)  # rule names waiting on this fact


class ReportSection(BaseModel):
    finding_id: str
    heading: str
    body: str
    why: str
    next_steps: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class ClinicReport(BaseModel):
    title: str
    subject: str
    lede: str
    findings: list[Finding]
    sections: list[ReportSection]
    numbers: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    packs_applied: list[str]
    disclaimer: str
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)


class IntakeRequest(BaseModel):
    text: str
    persona_id: str | None = None
    locale: str = "en"
    live: bool = True
    entity_type: EntityType | None = None
    income_band: IncomeBand | None = None
    has_family_trust: bool = False
    consider_property: bool = False
    consider_alcohol: bool = False
    consider_gst: bool = False
    jurisdictions: list[str] = Field(default_factory=list)


class UploadedDoc(BaseModel):
    name: str
    kind: str
    characters: int
    excerpt: str


class Layer1Engagement(BaseModel):
    role: str = "engagement_counsel"
    who: str
    entity_type: str
    income_band: str | None = None
    jurisdictions: list[str]
    documents: list[UploadedDoc] = Field(default_factory=list)
    assessment: str
    recommendations: list[str] = Field(default_factory=list)


class Layer2Analysis(BaseModel):
    role: str = "cpa_tax_attorney"
    model: str
    model_role: str
    upload_digest: str
    legal: list[str] = Field(default_factory=list)
    accounting: list[str] = Field(default_factory=list)
    rulings_applied: list[str] = Field(default_factory=list)


class AppliedStep(BaseModel):
    rule_id: str
    name: str
    inputs: list[str] = Field(default_factory=list)
    result: str
    citation_src: str
    citation_url: str
    passage: str = ""


class WorksheetLine(BaseModel):
    name: str
    inputs: list[str] = Field(default_factory=list)
    result: str
    note: str
    forms: list[str] = Field(default_factory=list)


class CalendarItem(BaseModel):
    date: str
    jurisdiction: str
    name: str
    form: str
    method: str = "MassTaxConnect"
    status: str = "pending"
    rule_id: str | None = None


class NexusCall(BaseModel):
    jurisdiction: str
    trigger: str
    nexus: str  # YES, REVIEW, NO
    tax_types: list[str] = Field(default_factory=list)


class AgencyMemo(BaseModel):
    role: str
    title: str
    summary: str
    items: list[str] = Field(default_factory=list)


class AgencyDocket(BaseModel):
    counsel: AgencyMemo
    accountant: AgencyMemo
    compliance: AgencyMemo
    review: AgencyMemo
    nexus: list[NexusCall] = Field(default_factory=list)
    worksheet: list[WorksheetLine] = Field(default_factory=list)
    calendar: list[CalendarItem] = Field(default_factory=list)


class Layer3Workpapers(BaseModel):
    role: str = "workpapers"
    steps: list[AppliedStep] = Field(default_factory=list)
    worksheet: list[WorksheetLine] = Field(default_factory=list)
    calendar: list[CalendarItem] = Field(default_factory=list)
    references: list[Citation] = Field(default_factory=list)


class ClinicLayers(BaseModel):
    engagement: Layer1Engagement
    analysis: Layer2Analysis
    workpapers: Layer3Workpapers


class CheckupResponse(BaseModel):
    profile: TaxProfile
    findings: list[Finding]
    report: ClinicReport
    extraction_source: str
    offline: bool = True
    agency: AgencyDocket | None = None
    layers: ClinicLayers | None = None
    questions: list[OpenQuestion] = Field(default_factory=list)

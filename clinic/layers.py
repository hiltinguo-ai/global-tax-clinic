from __future__ import annotations

from clinic.agency import run_agency
from clinic.explain import number_firewall
from clinic.models import ModelClient, pick_models, route_analyze, schema_of
from clinic.retrieve import retrieve_for
from clinic.schemas import (
    AppliedStep,
    Citation,
    ClinicLayers,
    Finding,
    FindingStatus,
    IncomeBand,
    Layer1Engagement,
    Layer2Analysis,
    Layer3Workpapers,
    TaxProfile,
    UploadedDoc,
)

BAND_LABEL = {
    IncomeBand.hnw: "high-net-worth individual",
    IncomeBand.middle: "middle-income individual",
    IncomeBand.low_income: "lower-income individual",
}

JURISDICTION_PACKS = {
    "us-federal": "us-federal",
    "massachusetts": "us-state-ma",
    "hong-kong": "hk-ird",
    "china-mainland": "cn-sta",
    "europe": "europe",
    "cross-border": "cross-border",
    "other-us-states": "us-state-nexus",
    "australia": "au-ato",
    "singapore": "sg-iras",
    "canada": "ca-cra",
    "united-kingdom": "uk-hmrc",
}

PACK_LABEL = {
    "us-federal": "US federal",
    "us-state-ma": "Massachusetts",
    "hk-ird": "Hong Kong IRD",
    "cn-sta": "China mainland (STA)",
    "europe": "Europe",
    "cross-border": "Cross-border",
    "us-state-nexus": "Other US states (review)",
    "au-ato": "Australia (ATO)",
    "sg-iras": "Singapore (IRAS)",
    "ca-cra": "Canada (CRA)",
    "uk-hmrc": "United Kingdom (HMRC)",
}


def pack_ids_for(jurisdictions: list[str]) -> list[str] | None:
    if not jurisdictions:
        return None
    ids = [JURISDICTION_PACKS[j] for j in jurisdictions if j in JURISDICTION_PACKS]
    return ids or None


def who_label(profile: TaxProfile) -> str:
    name = profile.display_name or "the client"
    trust = "with a family trust" if profile.has_family_trust and profile.entity_type.value != "family_trust" else ""
    if profile.entity_type.value == "llc":
        return f"{name} — limited liability company" + (f", {trust}" if trust else "")
    if profile.entity_type.value == "c_corp":
        return f"{name} — C corporation" + (f", {trust}" if trust else "")
    if profile.entity_type.value == "family_trust":
        extra = " holding a founder stake in a listed company" if profile.has_founder_listed_stake else ""
        return f"{name} — family trust{extra}"
    band = BAND_LABEL.get(profile.income_band) if profile.income_band else "individual"
    if trust:
        return f"{name} — {band}, {trust}"
    return f"{name} — {band}"


def build_layers(
    profile: TaxProfile,
    findings: list[Finding],
    docs: list[UploadedDoc],
    jurisdictions: list[str],
    client: ModelClient | None = None,
) -> ClinicLayers:
    agency = run_agency(profile, findings)
    required = [f for f in findings if f.status == FindingStatus.required]
    review = [n for n in agency.nexus if n.nexus == "REVIEW"]
    jur_labels = [PACK_LABEL.get(JURISDICTION_PACKS.get(j, j), j) for j in jurisdictions] or [
        PACK_LABEL.get(f.pack_id, f.jurisdiction) for f in findings
    ]
    jur_labels = list(dict.fromkeys(jur_labels))

    unsettled = [f for f in findings if f.confidence == "needs_facts"]
    assessment = (
        f"{who_label(profile)}. Counsel opened the file across "
        f"{', '.join(jur_labels) or 'the loaded packs'}. "
        f"{len(required)} obligation(s) look required"
        + (f", {len(unsettled)} more hinge on unconfirmed facts" if unsettled else "")
        + f"; {len(review)} jurisdiction(s) stay REVIEW. "
        "This is a preliminary engagement memo, not a return."
    )
    recs: list[str] = []
    for f in required[:5]:
        recs.append(f"Calendar {f.name}" + (f" — {f.deadline.date}" if f.deadline else "") + ".")
    for n in review[:4]:
        recs.append(f"Hold {n.jurisdiction}: {n.trigger}. Counsel has not confirmed nexus.")
    for f in findings:
        recs.extend(f.evidence_needed[:1])
    recs = list(dict.fromkeys(recs))[:8]
    if not recs:
        recs = ["Ask one follow-up: entity type, jurisdictions, and any foreign accounts or employees."]

    models = pick_models(client)
    memo_model = route_analyze(client, profile, findings)
    legal = list(agency.counsel.items)
    accounting = [f"{w.name}: {w.result} — {w.note}" for w in agency.worksheet]
    if client and memo_model:
        extra = _slm_analysis(client, memo_model, profile, findings, docs)
        if extra:
            legal = extra.get("legal_issues") or legal
            accounting = extra.get("accounting_issues") or accounting
            legal = [number_firewall(x, findings) for x in legal]
            accounting = [number_firewall(x, findings) for x in accounting]

    digest = (
        f"{len(docs)} document(s) read on device. "
        + "; ".join(f"{d.name} ({d.kind}, {d.characters} chars)" for d in docs[:6])
        if docs
        else "No PDF or zip was uploaded. Intake is the notes (and any sample file) only."
    )

    steps: list[AppliedStep] = []
    refs: list[Citation] = []
    for f in findings:
        cite = f.citations[0] if f.citations else Citation(src="pack", url="")
        passage = ""
        hits = retrieve_for(f, limit=1)
        if hits:
            passage = (hits[0].get("text") or "")[:360]
        steps.append(
            AppliedStep(
                rule_id=f.rule_id,
                name=f.name,
                inputs=[f.reason][:1],
                result=f"{f.status.value} · {f.severity.value}",
                citation_src=cite.src,
                citation_url=cite.url,
                passage=passage,
            )
        )
        refs.extend(f.citations)
    # de-dupe refs
    seen: set[str] = set()
    uniq: list[Citation] = []
    for c in refs:
        key = c.src + c.url
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    return ClinicLayers(
        engagement=Layer1Engagement(
            who=who_label(profile),
            entity_type="+".join(profile.types_on_file()),
            income_band=profile.income_band.value if profile.income_band else None,
            jurisdictions=jur_labels,
            documents=docs,
            assessment=assessment,
            recommendations=recs,
        ),
        analysis=Layer2Analysis(
            model=memo_model or models.get("analyze") or models.get("extract") or "packs + heuristic (no SLM running)",
            model_role=_memo_role(memo_model, models),
            upload_digest=digest,
            legal=legal,
            accounting=accounting,
            rulings_applied=[f"{f.rule_id} — {f.name}" for f in findings],
        ),
        workpapers=Layer3Workpapers(
            steps=steps,
            worksheet=agency.worksheet,
            calendar=agency.calendar,
            references=uniq,
        ),
    )


def _slm_analysis(client: ModelClient, model: str, profile: TaxProfile, findings: list[Finding], docs: list[UploadedDoc]) -> dict | None:
    from pydantic import BaseModel, Field

    class Memo(BaseModel):
        legal_issues: list[str] = Field(default_factory=list)
        accounting_issues: list[str] = Field(default_factory=list)

    excerpt = " ".join(d.excerpt for d in docs)[:1500]
    facts = "; ".join(m for f in findings for m in f.matched)[:1200]
    open_qs = "; ".join(q for f in findings for q in f.open_questions)[:600]
    user = (
        f"Profile: {profile.model_dump_json()}\n"
        f"Findings: {[f.rule_id + ':' + f.name + ' (' + f.status.value + ')' for f in findings]}\n"
        f"Established facts: {facts}\n"
        f"Unresolved questions: {open_qs}\n"
        f"Uploads: {excerpt}\n"
        "Write 3-6 short legal_issues and 3-6 accounting_issues, each one sentence, "
        "specific to THIS client. Copy numbers only from the profile or findings. "
        "Do not compute new amounts. Flag the unresolved questions worth chasing first."
    )
    bilingual = "qwen" in model.lower()
    system = (
        "You are a tax attorney and CPA on US, Hong Kong, and China mainland files. "
        "Narrate the pack findings only. Do not compute new amounts, rates, or deadlines. JSON only."
        if bilingual
        else "You are a US tax attorney and CPA. Narrate the pack findings only. "
        "Do not compute new amounts, rates, or deadlines. JSON only."
    )
    return client.generate_json(
        model=model,
        system=system,
        user=user,
        schema=schema_of(Memo),
    )


def _memo_role(memo_model: str | None, models: dict) -> str:
    if not memo_model:
        return "deterministic packs (SLM optional)"
    bilingual = models.get("bilingual")
    us_tax = models.get("us_tax")
    if bilingual and us_tax and bilingual != us_tax:
        if "qwen" in memo_model.lower():
            return f"bilingual explainer · US-tax desk {us_tax} on standby"
        return f"US-tax explainer · bilingual desk {bilingual} on standby"
    if "qwen" in memo_model.lower():
        return "bilingual explainer / legal-accounting memo"
    return "US-tax explainer / legal-accounting memo"

from __future__ import annotations

from clinic.agency import run_agency
from clinic.documents import ingest_files
from clinic.engine import evaluate_detailed
from clinic.explain import explain
from clinic.extract import extract
from clinic.layers import build_layers, pack_ids_for
from clinic.models import ModelClient, pick_models
from clinic.schemas import (
    AlcoholLine,
    CheckupResponse,
    EntityType,
    GstSupply,
    IncomeBand,
    PublicCompanyStake,
    RealProperty,
    TaxProfile,
    UploadedDoc,
)


def apply_engagement(
    profile: TaxProfile,
    entity_type: EntityType | None,
    income_band: IncomeBand | None,
    jurisdictions: list[str],
    founder_listed: bool = False,
    has_family_trust: bool = False,
    consider_property: bool = False,
    consider_alcohol: bool = False,
    consider_gst: bool = False,
) -> TaxProfile:
    data = profile.model_dump()
    if entity_type:
        data["entity_type"] = entity_type
    if income_band:
        data["income_band"] = income_band
    if has_family_trust or entity_type == EntityType.family_trust:
        data["has_family_trust"] = True
    residencies = list(data.get("residencies") or [])
    states = list(data.get("states") or [])
    for j in jurisdictions:
        if j == "us-federal" and "US" not in residencies:
            residencies.append("US")
        if j == "massachusetts" and "MA" not in states:
            states.append("MA")
        if j == "hong-kong" and "HK" not in residencies:
            residencies.append("HK")
        if j == "china-mainland" and "CN" not in residencies:
            residencies.append("CN")
        if j == "europe" and "EU" not in residencies:
            residencies.append("EU")
        if j == "australia" and "AU" not in residencies:
            residencies.append("AU")
        if j == "singapore" and "SG" not in residencies:
            residencies.append("SG")
        if j == "canada" and "CA" not in residencies:
            residencies.append("CA")
        if j == "united-kingdom" and "UK" not in residencies:
            residencies.append("UK")
    data["residencies"] = residencies
    data["states"] = states
    props = list(data.get("properties") or [])
    if consider_property and not props:
        if "MA" in states:
            props.append(RealProperty(country="US", state="MA").model_dump())
        if "HK" in residencies:
            props.append(RealProperty(country="HK").model_dump())
        if "CN" in residencies:
            props.append(RealProperty(country="CN").model_dump())
        if "AU" in residencies:
            props.append(RealProperty(country="AU").model_dump())
        if "SG" in residencies:
            props.append(RealProperty(country="SG").model_dump())
        if "UK" in residencies:
            props.append(RealProperty(country="UK").model_dump())
        if "CA" in residencies:
            props.append(RealProperty(country="CA").model_dump())
        if not props:
            props.append(RealProperty(country="US").model_dump())
    data["properties"] = props
    drinks = list(data.get("alcohol") or [])
    if consider_alcohol and not drinks:
        role = "restaurant" if data.get("has_restaurant") else "retail"
        if "MA" in states:
            drinks.append(AlcoholLine(country="US", state="MA", kind="wine", role=role, licensed=True).model_dump())
        if "HK" in residencies:
            drinks.append(AlcoholLine(country="HK", kind="wine", role="importer", licensed=True).model_dump())
        if "AU" in residencies:
            drinks.append(AlcoholLine(country="AU", kind="wine", role="wholesale", licensed=True).model_dump())
        if "UK" in residencies:
            drinks.append(AlcoholLine(country="UK", kind="wine", role=role, licensed=True).model_dump())
        if "EU" in residencies:
            drinks.append(AlcoholLine(country="EU", kind="wine", role="importer", licensed=True).model_dump())
        if "CN" in residencies:
            drinks.append(AlcoholLine(country="CN", kind="spirits", role="producer", licensed=True).model_dump())
        if "CA" in residencies:
            drinks.append(AlcoholLine(country="CA", kind="wine", role=role, licensed=True).model_dump())
        if not drinks:
            drinks.append(AlcoholLine(country="US", kind="wine", role=role, licensed=True).model_dump())
    data["alcohol"] = drinks
    gst = list(data.get("gst_supplies") or [])
    if consider_gst and not gst:
        for j, code in (
            ("australia", "AU"),
            ("singapore", "SG"),
            ("canada", "CA"),
            ("united-kingdom", "UK"),
            ("europe", "EU"),
            ("china-mainland", "CN"),
        ):
            if j in jurisdictions:
                gst.append(GstSupply(country=code).model_dump())
    data["gst_supplies"] = gst
    stakes = list(data.get("public_stakes") or [])
    if founder_listed and not stakes:
        stakes.append(
            PublicCompanyStake(
                name="listed company (engagement)",
                country="US",
                listed=True,
                ownership_pct="0",
                years_held=20,
                founded_by_client=True,
            ).model_dump()
        )
    data["public_stakes"] = stakes
    # engagement answers are established facts too
    provided = set(data.get("facts_provided") or [])
    if entity_type:
        provided.add("entity_type")
    if income_band:
        provided.add("income_band")
    if jurisdictions:
        provided.update({"residencies", "states"})
    if founder_listed:
        provided.add("public_stakes")
    if has_family_trust or entity_type == EntityType.family_trust:
        provided.add("has_family_trust")
    if consider_property:
        provided.add("properties")
    if consider_alcohol:
        provided.add("alcohol")
    if consider_gst:
        provided.add("gst_supplies")
    if provided:
        data["facts_provided"] = sorted(provided)
    return TaxProfile.model_validate(data)


def run_visit(
    text: str,
    persona_id: str | None = None,
    live: bool = True,
    entity_type: EntityType | None = None,
    income_band: IncomeBand | None = None,
    jurisdictions: list[str] | None = None,
    files: list[tuple[str, bytes]] | None = None,
    founder_listed: bool = False,
    has_family_trust: bool = False,
    consider_property: bool = False,
    consider_alcohol: bool = False,
    consider_gst: bool = False,
    client: ModelClient | None = None,
) -> CheckupResponse:
    jurisdictions = jurisdictions or []
    client = client or ModelClient()
    models = pick_models(client)
    extra, docs = ingest_files(files or [])
    combined = text.strip()
    if extra:
        combined = f"{combined}\n\n{extra}".strip()
    slm_ready = bool(models.get("bilingual") or models.get("us_tax") or models.get("extract"))
    profile, source = extract(
        combined,
        persona_id=persona_id,
        client=client if slm_ready else None,
        live=live,
    )
    profile = apply_engagement(
        profile,
        entity_type,
        income_band,
        jurisdictions,
        founder_listed=founder_listed,
        has_family_trust=has_family_trust,
        consider_property=consider_property,
        consider_alcohol=consider_alcohol,
        consider_gst=consider_gst,
    )
    findings, metas, questions = evaluate_detailed(profile, pack_ids=pack_ids_for(jurisdictions))
    report = explain(profile, findings, metas, questions)
    agency = run_agency(profile, findings)
    layers = build_layers(profile, findings, docs, jurisdictions, client=client)
    return CheckupResponse(
        profile=profile,
        findings=findings,
        report=report,
        extraction_source=source,
        offline=False,
        agency=agency,
        layers=layers,
        questions=questions,
    )

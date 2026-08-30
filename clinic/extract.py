from __future__ import annotations

import re

from clinic.models import ModelClient, schema_of
from clinic.personas import PERSONA_TRANSCRIPTS, PROFILES
from clinic.schemas import (
    AlcoholLine,
    EntityType,
    ForeignAccount,
    Gift,
    GstSupply,
    IncomeStream,
    LifeEvent,
    OwnershipLink,
    PublicCompanyStake,
    RealProperty,
    StateRevenue,
    TaxProfile,
)

EXTRACTOR_SYSTEM = """You extract a TaxProfile JSON for a tax compliance clinic.

Rules, in order of importance:
1. Only use facts stated in the intake. Never guess or invent amounts, countries,
   account balances, or entity types. A field the intake does not mention stays
   null / empty / default.
2. If the intake explicitly denies something ("no foreign accounts"), return the
   empty value for it — that is a real fact, not a missing one.
3. Amounts: convert to plain USD numbers ("18万美元" -> 180000, "$3.2k" -> 3200).
4. entity_type: individual | llc | c_corp | family_trust.
   If the intake is about a person who also has a family trust, entity_type
   is individual and has_family_trust is true. Use family_trust only when
   the trust itself is the client.
5. income_streams[].kind: w2 | tips | 1099_nec | rental | rsu | interest | sales.
6. foreign_accounts[].kind: bank | brokerage | fund | mpf | housing_fund.
   properties[]: country, state, kind (residential|commercial|rental), rental bool.
   alcohol[]: kind (wine|beer|spirits), role (producer|importer|wholesale|retail|restaurant).
   gst_supplies[]: country AU|SG|CA|UK|EU|CN, registered bool if stated.
   max_balance_usd is the YEAR-MAX balance; use 0 only if truly unstated.
7. Return JSON only. No prose.
"""

_ALL_FACTS = [f for f in TaxProfile.model_fields if f not in {"notes", "facts_provided", "tax_year"}]
_DEFAULTS = TaxProfile().model_dump()

_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington state": "WA", "west virginia": "WV", "wisconsin": "WI",
    "wyoming": "WY",
}
_CITY_STATE = {"boston": "MA", "worcester": "MA", "cambridge, ma": "MA", "nyc": "NY", "manhattan": "NY"}

_MONTHS = {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
)}


def _date_near(text: str, keyword_rx: str, window: int = 90) -> str | None:
    """ISO date found within `window` chars of a keyword match, if any."""
    m = re.search(keyword_rx, text, re.I)
    if not m:
        return None
    lo = max(0, m.start() - window)
    hi = min(len(text), m.end() + window)
    seg = text[lo:hi]
    d = re.search(r"(\d{4})-(\d{2})-(\d{2})", seg)
    if d:
        return d.group(0)
    d = re.search(r"(\d{1,2})\s+([a-z]{3,9})\.?\s+(\d{4})", seg, re.I)  # 1 August 2026
    if d and d.group(2)[:3].lower() in _MONTHS:
        return f"{d.group(3)}-{_MONTHS[d.group(2)[:3].lower()]:02d}-{int(d.group(1)):02d}"
    d = re.search(r"([a-z]{3,9})\.?\s+(\d{1,2})(?!\d),?\s*(\d{4})?", seg, re.I)  # July 15, 2026
    if d and d.group(1)[:3].lower() in _MONTHS and int(d.group(2)) <= 31:
        year = d.group(3) or "2026"
        return f"{year}-{_MONTHS[d.group(1)[:3].lower()]:02d}-{int(d.group(2)):02d}"
    d = re.search(r"\bin\s+([a-z]{3,9})\b", seg, re.I)  # "in July" -> mid-month
    if d and d.group(1)[:3].lower() in _MONTHS:
        return f"2026-{_MONTHS[d.group(1)[:3].lower()]:02d}-15"
    return None


_NUM_WORDS = {
    "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def extract(
    text: str,
    persona_id: str | None = None,
    client: ModelClient | None = None,
    live: bool = True,
) -> tuple[TaxProfile, str]:
    if persona_id and persona_id in PROFILES:
        profile = PROFILES[persona_id]()
        # gold personas are complete files: every field is an established fact
        return profile.model_copy(update={"facts_provided": list(_ALL_FACTS)}), f"persona:{persona_id}"

    if not live:
        matched = _match_persona(text)
        if matched:
            profile = PROFILES[matched]()
            return profile.model_copy(update={"facts_provided": list(_ALL_FACTS)}), f"persona:{matched}"

    heuristic = _heuristic(text)

    if client and text.strip():
        from clinic.models import route_extract

        model = route_extract(client, text)
        if model:
            raw = client.generate_json(
                model=model,
                system=EXTRACTOR_SYSTEM,
                user=f"Intake notes:\n{text[:5000]}",
                schema=schema_of(TaxProfile),
            )
            if raw:
                try:
                    raw.pop("facts_provided", None)
                    modeled = TaxProfile.model_validate(raw)
                    merged = _merge(modeled, heuristic, text)
                    return merged, f"ollama:{model}+heuristic"
                except Exception:
                    pass  # fall through to pure heuristic

    return heuristic, "heuristic"


def _non_default_fields(profile: TaxProfile) -> set[str]:
    dump = profile.model_dump()
    out: set[str] = set()
    for f in _ALL_FACTS:
        if dump.get(f) != _DEFAULTS.get(f):
            out.add(f)
    return out


def _merge(modeled: TaxProfile, heuristic: TaxProfile, text: str) -> TaxProfile:
    """Model output wins where it said something; heuristics fill the gaps.

    facts_provided is the union of what either side actually established, plus
    explicit denials the heuristic detected in the text.
    """
    data = modeled.model_dump()
    hdump = heuristic.model_dump()
    model_known = _non_default_fields(modeled)
    heur_known = set(heuristic.facts_provided)
    for f in _ALL_FACTS:
        if f not in model_known and f in heur_known:
            data[f] = hdump[f]
    data["notes"] = text[:400]
    data["facts_provided"] = sorted(model_known | heur_known)
    return TaxProfile.model_validate(data)


def _match_persona(text: str) -> str | None:
    blob = text.strip()
    for key, meta in PERSONA_TRANSCRIPTS.items():
        for sample in (meta.get("text_en") or "", meta.get("text_zh") or ""):
            if sample and (blob == sample or sample[:40] in blob or blob[:40] in sample):
                return key
    lowered = blob.lower()
    if "强积金" in blob or "深圳" in blob or ("mei" in lowered and "hong kong" in lowered):
        return "mei"
    if "doordash" in lowered or ("tips" in lowered and "new hampshire" in lowered):
        return "luis"
    if "sichuan garden" in lowered or ("meals" in lowered and "llc" in lowered):
        return "sichuan"
    if "nori" in lowered or ("shanghai" in lowered and "delaware" in lowered):
        return "nori"
    if "nimbus" in lowered or "nimbusflow" in lowered:
        return "nimbus"
    if "chen family" in lowered or "northline" in lowered:
        return "chen"
    return None


# --------------------------------------------------------------------------
# amounts: "$3,200", "3200 USD", "3.2k", "1.5m", "18万美元", bare "180,000"
# --------------------------------------------------------------------------

_AMOUNT_RX = re.compile(
    r"""
    (?:\$|hk\$|us\$)\s?(?P<a>\d[\d,]*(?:\.\d+)?)\s*(?P<suf_a>[km])?
    | (?P<b>\d[\d,]*(?:\.\d+)?)\s*(?P<suf_b>[km])?\s*(?:usd|dollars|美元|美金)
    | (?P<wan>\d+(?:\.\d+)?)\s*万(?:\s*(?:美元|美金))?
    | (?P<c>\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b)
    | (?P<d>\b\d{3,9}\b)
    """,
    re.I | re.X,
)


def _amounts(text: str) -> list[tuple[float, int, int]]:
    out: list[tuple[float, int, int]] = []
    for m in _AMOUNT_RX.finditer(text):
        if m.group("wan"):
            val = float(m.group("wan")) * 10_000
        else:
            raw = m.group("a") or m.group("b") or m.group("c") or m.group("d")
            if raw is None:
                continue
            val = float(raw.replace(",", ""))
            suf = (m.group("suf_a") or m.group("suf_b") or "").lower()
            if suf == "k":
                val *= 1_000
            elif suf == "m":
                val *= 1_000_000
        out.append((val, m.start(), m.end()))
    return out


def _context(text: str, start: int, end: int, back: int = 70, fwd: int = 40) -> str:
    return text[max(0, start - back) : min(len(text), end + fwd)].lower()


def _denied(t: str, *phrases: str) -> bool:
    for p in phrases:
        for neg in ("no ", "without ", "don't have ", "do not have ", "none of ", "never had "):
            if neg + p in t:
                return True
    return False


def _heuristic(text: str) -> TaxProfile:
    t = text.lower()
    provided: set[str] = set()

    # ---- entity ----------------------------------------------------------
    # An employer named "X Inc." on a resume must not turn the client into a
    # C-corp: entity words only win when the text is ABOUT an entity, or when
    # there is no first-person / personal-document signal.
    individual_signal = bool(
        re.search(r"\bi am\b|\bi'm\b|\bmy\b", t)
        or "personal financial statement" in t
        or "resume" in t
        or "head of household" in t
        or "filing single" in t
        or re.search(r"individual\b", t)
        or "我" in text
    )
    company_subject = bool(
        re.search(r"is a [^.\n]{0,60}(llc|c[- ]?corp|corporation|family trust)", t)
        or "the company" in t
        or "the trust" in t
        or "single-member llc" in t
    )
    entity = EntityType.individual
    mentions_trust = "family trust" in t or "grantor trust" in t
    has_family_trust = mentions_trust
    if mentions_trust and not individual_signal:
        entity = EntityType.family_trust
    elif company_subject or not individual_signal:
        if re.search(r"\bc[- ]corp", t) or re.search(r"\bcorporation\b", t) or (
            "inc." in t and not individual_signal
        ):
            entity = EntityType.c_corp
        elif re.search(r"\bllc\b", t):
            entity = EntityType.llc
    if entity == EntityType.individual and company_subject and re.search(r"\bllc\b", t) and "family trust" not in t:
        entity = EntityType.llc
    if entity != EntityType.individual or individual_signal:
        provided.add("entity_type")
    if mentions_trust:
        provided.add("has_family_trust")

    # ---- US person -------------------------------------------------------
    us_person = False
    if any(
        x in t
        for x in (
            "us person", "u.s. person", "us citizen", "u.s. citizen", "american citizen",
            "green card", "green-card", "us resident", "us tax resident",
        )
    ) or "美国税务居民" in text or "美国公民" in text:
        us_person = True
        provided.add("us_person")
    if _denied(t, "us person") or "not a us person" in t or "non-us person" in t:
        us_person = False
        provided.add("us_person")
    if entity != EntityType.individual and ("owner is a us person" in t or "us owner" in t):
        us_person = True
        provided.add("us_person")

    # ---- residencies -----------------------------------------------------
    residencies: list[str] = []
    if us_person or any(x in t for x in ("united states", "us resident", "american")) or "美国" in text:
        residencies.append("US")
    if any(x in t for x in ("hong kong", "hsbc", "hang seng")) or "香港" in text or re.search(r"\bhk\b", t):
        residencies.append("HK")
    if any(x in t for x in ("mainland", "shenzhen", "shanghai", "beijing")) or re.search(r"\bchina\b", t) or any(
        x in text for x in ("中国", "深圳", "上海", "北京", "国内")
    ):
        residencies.append("CN")
    if residencies:
        provided.add("residencies")

    # ---- states ----------------------------------------------------------
    states: list[str] = []
    for name, abbr in _STATES.items():
        if name in t and abbr not in states:
            states.append(abbr)
    for city, abbr in _CITY_STATE.items():
        if city in t and abbr not in states:
            states.append(abbr)
    for m in re.finditer(r"\b(MA|NH|NY|CA|DE|TX|FL|WA|CT|RI|VT|NJ|PA)\b", text):
        if m.group(1) not in states:
            states.append(m.group(1))
    part_year: list[str] = []
    move_date = None
    move_from = move_to = None
    if "moved" in t or "part-year" in t or "part year" in t:
        part_year = list(states)
        provided.add("part_year_states")
        provided.add("life_events")
        move_date = _date_near(text, r"moved")
        m2 = re.search(r"moved (?:from )?([a-z ]{2,20}?) to ([a-z ]{2,20}?)(?:[.,;\n]| on | in )", t)
        if m2:
            move_from = _STATES.get(m2.group(1).strip(), None)
            move_to = _STATES.get(m2.group(2).strip(), None)
    if states:
        provided.add("states")

    # ---- days in mainland China -----------------------------------------
    days_in_cn: int | None = None
    m = re.search(r"(\d{1,3})\s*days?\s+(?:in|inside)\s+(?:mainland\s+)?china", t)
    if not m:
        m = re.search(r"在(?:中国|国内|大陆)[^\d]{0,8}(\d{1,3})\s*天", text)
    if m:
        days_in_cn = int(m.group(1))
        provided.add("days_in_cn")

    # ---- foreign accounts ------------------------------------------------
    accounts: list[ForeignAccount] = []
    balances_known = True
    if _denied(t, "foreign account", "foreign accounts", "overseas account", "foreign bank"):
        provided.add("foreign_accounts")
    else:
        amounts = _amounts(text)

        def nearest_amount(pos: int, used: set[int]) -> float | None:
            best, best_d = None, 10_000
            for i, (val, s, e) in enumerate(amounts):
                if i in used or val < 100:
                    continue
                ctx = _context(text, s, e, back=40, fwd=25)
                if "gift" in ctx or "赠" in ctx or "payroll" in ctx or "revenue" in ctx or "sales" in ctx:
                    continue
                d = abs(s - pos)
                if d < best_d and d < 90:
                    best, best_d = i, d
            if best is None:
                return None
            used.add(best)
            return amounts[best][0]

        used: set[int] = set()

        def best_occurrence(word: str) -> tuple[int | None, float | None]:
            """(amount_index, value) for the keyword occurrence closest to a usable
            amount. Pass 1: same line only — an xlsx table row is one line, and a
            neighboring row's amount must never be claimed (zips repeat tables).
            Pass 2 (only if pass 1 found nothing): proximity window, for PDFs
            whose tables extract one CELL per line."""
            for same_line_only in (True, False):
                best_i, best_val, best_d = None, None, 10_000.0
                for m2 in re.finditer(re.escape(word), text, re.I):
                    pos = m2.start()
                    ls = text.rfind("\n", 0, pos) + 1
                    le = text.find("\n", pos)
                    le = le if le != -1 else len(text)
                    for i, (val, s2, e2) in enumerate(amounts):
                        if i in used or val < 100:
                            continue
                        if same_line_only and (s2 < ls or e2 > le):
                            continue
                        if not same_line_only and abs(s2 - pos) > 110:
                            continue
                        ctx = _context(text, s2, e2, back=55, fwd=6)
                        if any(x in ctx for x in ("gift", "赠", "payroll", "revenue", "sales", "aggregate", "total")):
                            continue
                        d = (s2 - pos) * 1.0 if s2 >= pos else (pos - s2) * 1.6
                        if d < best_d:
                            best_i, best_val, best_d = i, val, d
                if best_i is not None:
                    return best_i, best_val
            return None, None

        account_words = [
            ("hsbc", "bank", "HK"), ("hang seng", "bank", "HK"), ("汇丰", "bank", "HK"),
            ("恒生", "bank", "HK"), ("brokerage", "brokerage", "HK"), ("券商", "brokerage", "HK"),
            ("mpf", "mpf", "HK"), ("强积金", "mpf", "HK"), ("housing fund", "housing_fund", "CN"),
            ("公积金", "housing_fund", "CN"), ("equity fund", "fund", "HK"),
            ("基金", "fund", "HK"),
        ]
        for word, kind, country in account_words:
            if not re.search(re.escape(word), text, re.I):
                continue
            idx, amt = best_occurrence(word)
            if idx is not None:
                used.add(idx)
            accounts.append(
                ForeignAccount(
                    country=country,
                    label=word.upper() if word.isascii() else kind,
                    kind=kind,
                    max_balance_usd=str(amt) if amt is not None else "0",
                )
            )
            if amt is None:
                balances_known = False
        if not accounts and (
            re.search(r"(hong kong|overseas|foreign|offshore)\s+(bank\s+)?accounts?", t) or "海外账户" in text
        ):
            # accounts exist, balances unstated -> stays an open question
            accounts.append(ForeignAccount(country="HK", label="foreign account", kind="bank", max_balance_usd="0"))
            balances_known = False
        if accounts and balances_known:
            provided.add("foreign_accounts")

    # ---- income streams --------------------------------------------------
    def _income_amt(*keywords: str) -> str | None:
        """Largest amount on a line that names this income kind (table rows)."""
        best = None
        for val, s2, e2 in _amounts(text):
            ls = text.rfind("\n", 0, s2) + 1
            le = text.find("\n", e2)
            line = text[ls : le if le != -1 else len(text)]
            if not re.search(r"[a-z]{3}", line, re.I):
                pls = text.rfind("\n", 0, max(ls - 1, 0)) + 1
                line = text[pls : ls - 1] + " " + line
            line = line.lower()
            if any(x in line for x in ("balance", "account", "aggregate", "total", "gift", "tax ")):
                continue
            if any(k in line for k in keywords) and val >= 100:
                best = max(best or 0, val)
        return str(best) if best else None

    streams: list[IncomeStream] = []
    if "w-2" in t or "w2" in t or "wait tables" in t or ("salary" in t and "employer" in t):
        streams.append(IncomeStream(kind="w2", country="US", amount_usd=_income_amt("w-2", "w2", "wages")))
    if re.search(r"\btips?\b", t) or "cash tips" in t:
        streams.append(IncomeStream(kind="tips", country="US", amount_usd=_income_amt("tips")))
    if "1099" in t or "doordash" in t or "uber" in t or re.search(r"\bgig\b", t) or "freelance" in t:
        streams.append(IncomeStream(kind="1099_nec", country="US", amount_usd=_income_amt("1099", "doordash", "gig", "delivery")))
    if re.search(r"\brent(?:s|al|ed|ing)?\b|rent out", t) or "出租" in text:
        country = "CN" if ("shenzhen" in t or "深圳" in text or "国内" in text) else "US"
        streams.append(IncomeStream(kind="rental", country=country))
    if "rsu" in t:
        streams.append(IncomeStream(kind="rsu", country="US"))
    if entity in {EntityType.llc, EntityType.c_corp} and ("restaurant" in t or "sales" in t or "sell" in t):
        streams.append(IncomeStream(kind="sales", country="US", state=states[0] if states else None))
    if streams:
        provided.add("income_streams")

    # ---- gifts -----------------------------------------------------------
    gifts: list[Gift] = []
    if _denied(t, "gift", "gifts"):
        provided.add("gifts")
    elif "gift" in t or "赠与" in text or "赠" in text:
        gift_amt: float | None = None
        for val, s, e in _amounts(text):
            ctx = _context(text, s, e)
            if "gift" in ctx or "赠" in ctx or "parents" in ctx or "父母" in ctx:
                gift_amt = max(gift_amt or 0, val)
        source = "CN" if ("china" in t or "国内" in text or "中国" in text or "parents" in t) else "unknown"
        if gift_amt:
            gifts.append(Gift(from_foreign_person=True, source_country=source, amount_usd=str(gift_amt)))
            provided.add("gifts")
        # gift mentioned but amount missing -> leave unprovided, becomes a question

    # ---- ownership of foreign entities ----------------------------------
    ownerships: list[OwnershipLink] = []
    if _denied(t, "foreign subsidiary", "foreign subsidiaries", "subsidiaries", "subsidiary"):
        provided.add("ownerships")
    else:
        m = re.search(r"\b(subsidiary|wfoe|holding company)\s+(?:company\s+)?in\s+([a-z ]{3,20})", t)
        if m or "shanghai subsidiary" in t:
            place = (m.group(2).strip() if m else "shanghai").split()[0]
            country = "CN" if place in {"shanghai", "shenzhen", "beijing", "china"} else place.upper()[:2]
            ownerships.append(OwnershipLink(name=f"{place} subsidiary", country=country, ownership_pct="100"))
            provided.add("ownerships")

    # ---- life events -----------------------------------------------------
    events: list[LifeEvent] = []
    if "83(b)" in t or "unvested" in t or "founder stock" in t or "equity grant" in t:
        grant_date = _date_near(text, r"grant") or _date_near(text, r"founder stock")
        events.append(LifeEvent(kind="equity_grant", date=grant_date))
        provided.add("life_events")
    if part_year:
        events.append(LifeEvent(kind="move_state", date=move_date, from_state=move_from, to_state=move_to))

    # ---- dependents ------------------------------------------------------
    dependents = 0
    if _denied(t, "children", "kids", "dependents"):
        provided.add("dependents")
    else:
        m = re.search(r"(\d+|one|two|three|four|five|a)\s+(?:child(?:ren)?|kids?|dependents?)", t)
        if m:
            token = m.group(1)
            dependents = int(token) if token.isdigit() else _NUM_WORDS.get(token, 1)
            provided.add("dependents")

    # ---- business flags --------------------------------------------------
    has_restaurant = "restaurant" in t or "meals" in t or "餐馆" in text
    if has_restaurant:
        provided.add("has_restaurant")
    has_employees = False
    if _denied(t, "employees"):
        provided.add("has_employees")
    elif any(x in t for x in ("employees", "payroll", "staff", "waiters", "waitstaff")):
        has_employees = True
        provided.add("has_employees")

    industry = None
    if "saas" in t or "software" in t:
        industry = "saas"
    elif has_restaurant:
        industry = "restaurant"
    elif "robotics" in t:
        industry = "robotics"
    if industry:
        provided.add("industry")

    properties: list[RealProperty] = []
    if any(x in t for x in ("real estate", "real property", "property tax", "condo", "apartment", "assessed value", "rateable")) or "房产" in text:
        country = "HK" if "hong kong" in t or "香港" in text else ("CN" if "shenzhen" in t or "shanghai" in t or "china" in t else "US")
        state = "MA" if "massachusetts" in t or "boston" in t or "brookline" in t else None
        properties.append(
            RealProperty(country=country, state=state, kind="rental" if "rent" in t else "residential", rental="rent" in t)
        )
        provided.add("properties")

    alcohol: list[AlcoholLine] = []
    if any(x in t for x in ("wine", "winery", "liquor", "abcc", "alcohol license", "spirits", "brewery")):
        role = "producer" if any(x in t for x in ("winery", "producer", "importer", "brewery")) else (
            "restaurant" if has_restaurant else "retail"
        )
        if "import" in t:
            role = "importer"
        kind = "spirits" if "spirits" in t or "liquor" in t else ("beer" if "beer" in t or "brewery" in t else "wine")
        st = "MA" if "massachusetts" in t or "boston" in t else None
        alcohol.append(AlcoholLine(country="US", state=st, kind=kind, role=role, licensed=True))
        provided.add("alcohol")

    gst_supplies: list[GstSupply] = []
    gst_map = (
        ("australia", "AU"), ("ato", "AU"), ("singapore", "SG"), ("iras", "SG"),
        ("canada", "CA"), ("hst", "CA"), ("united kingdom", "UK"), ("hmrc", "UK"),
        ("europe", "EU"), (" oss", "EU"),
    )
    seen_gst: set[str] = set()
    if "vat" in t or "gst" in t or "hst" in t:
        for needle, code in gst_map:
            if needle in t and code not in seen_gst:
                seen_gst.add(code)
                gst_supplies.append(GstSupply(country=code, registered=True))
        if "增值税" in text and "CN" not in seen_gst:
            gst_supplies.append(GstSupply(country="CN", registered=None))
        if gst_supplies:
            provided.add("gst_supplies")

    incorporation_state = None
    m = re.search(r"incorporated in ([a-z ]{4,20})", t)
    if m:
        incorporation_state = _STATES.get(m.group(1).strip(), m.group(1).strip().upper()[:2])
        provided.add("incorporation_state")
    elif entity == EntityType.c_corp and "delaware" in t:
        incorporation_state = "DE"
        provided.add("incorporation_state")

    # ---- revenue by state ------------------------------------------------
    revenue: list[StateRevenue] = []
    by_state: dict[str, float] = {}
    for val, s, e in _amounts(text):
        # attribution is line-scoped: a table row is one line, and a
        # neighboring row's state must not claim this row's amounts
        ls = text.rfind("\n", 0, s) + 1
        le = text.find("\n", e)
        line = text[ls : le if le != -1 else len(text)]
        if not re.search(r"[a-z]{3}", line, re.I):
            # amount-only line: a PDF table wrapped the row — label is above
            pls = text.rfind("\n", 0, max(ls - 1, 0)) + 1
            line = text[pls : ls - 1] + " " + line
            ls = pls
        low = line.lower()
        if "sales" not in low and "revenue" not in low:
            continue
        before = line[: s - ls]
        if re.search(r"total[^0-9]{0,24}$", before, re.I):
            continue  # grand-total rows belong to no single state
        state = None
        best = -1
        for name, abbr in _STATES.items():
            i = low.rfind(name, 0, s - ls)
            if i > best:
                best, state = i, abbr
        for m2 in re.finditer(r"\b(MA|NH|NY|CA|DE|TX|FL|WA|IL|CT|RI|VT|NJ|PA)\b", before):
            if m2.start() > best:
                best, state = m2.start(), m2.group(1)
        if state:
            # a row lists quarters AND a row total: keep the max (the total)
            by_state[state] = max(by_state.get(state, 0), val)
    for abbr, val in by_state.items():
        revenue.append(StateRevenue(state=abbr, amount_usd=str(val)))
    if revenue:
        provided.add("revenue_by_state")

    # ---- founder public stake --------------------------------------------
    stakes: list[PublicCompanyStake] = []
    founderish = any(x in t for x in ("founded", "took public", "ipo", "listed", "public company"))
    stakeish = any(x in t for x in ("percent", "%", "owns", "stake", "shares"))
    if founderish and (stakeish or "20 year" in t or "twenty year" in t):
        pct = "0"
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", t)
        if m:
            pct = m.group(1)
        years = 20
        ym = re.search(r"(\d{1,2})\s+years?", t)
        if ym:
            years = int(ym.group(1))
        country = "US"
        if any(x in t for x in ("hong kong", "hkex")):
            country = "HK"
        elif "china" in t or "shanghai" in t or "shenzhen" in t:
            country = "CN"
        stakes.append(
            PublicCompanyStake(
                name="listed company", country=country, listed=True,
                ownership_pct=pct, years_held=years, founded_by_client=True,
            )
        )
        provided.add("public_stakes")

    chinese_founders = "chinese founder" in t or "founders are chinese" in t
    if chinese_founders:
        provided.add("chinese_founders")

    return TaxProfile(
        entity_type=entity,
        has_family_trust=has_family_trust,
        us_person=us_person,
        public_stakes=stakes,
        residencies=residencies or (["US"] if us_person else []),
        states=states,
        part_year_states=part_year,
        days_in_cn=days_in_cn,
        dependents=dependents,
        foreign_accounts=accounts,
        income_streams=streams,
        ownerships=ownerships,
        gifts=gifts,
        life_events=events,
        properties=properties,
        alcohol=alcohol,
        gst_supplies=gst_supplies,
        has_restaurant=has_restaurant,
        has_employees=has_employees,
        chinese_founders=chinese_founders,
        industry=industry,
        incorporation_state=incorporation_state,
        revenue_by_state=revenue,
        notes=text[:400],
        facts_provided=sorted(provided),
    )

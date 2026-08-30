"""Three-desk agency on top of the packs.

Counsel reads nexus and obligations (engine).
Accountant turns confirmed facts into a worksheet (code, never a model).
Compliance builds the calendar and document list (code).
Counsel review is the legal gate — REVIEW items do not proceed to 'file'.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from clinic.schemas import (
    AgencyDocket,
    AgencyMemo,
    CalendarItem,
    Finding,
    FindingStatus,
    NexusCall,
    TaxProfile,
    WorksheetLine,
)

MONEY = Decimal("0.01")
MA_SALES_TAX = Decimal("0.0625")
MA_MEALS_LOCAL = Decimal("0.0075")
MA_EXCISE_MIN = Decimal("456")
MA_SALES_NEXUS = Decimal("100000")
ST9_MONTHLY_THRESHOLD = Decimal("1200")
FBAR_THRESHOLD = Decimal("10000")
GIFT_3520_THRESHOLD = Decimal("100000")
SE_RATE = Decimal("0.153")
SE_BASE_FACTOR = Decimal("0.9235")
SE_FLOOR = Decimal("400")
FOREIGN_OWNER_5472 = Decimal("25")


def _money(n: Decimal) -> str:
    return f"{n.quantize(MONEY, rounding=ROUND_HALF_UP):,.2f}"


def _pct(n: Decimal) -> str:
    return f"{(n * Decimal('100')).quantize(Decimal('0.01'))}%"


def _has(findings: list[Finding], rule_id: str) -> bool:
    return any(f.rule_id == rule_id for f in findings)


def _has_confirmed(findings: list[Finding], rule_id: str) -> bool:
    """The rule actually fired on established facts — a tri-logic 'check'
    (unknown facts) must not produce an illustrated tax amount."""
    return any(
        f.rule_id == rule_id and f.confidence == "confirmed" and f.status.value in {"required", "likely"}
        for f in findings
    )


def _nexus_table(profile: TaxProfile, findings: list[Finding]) -> list[NexusCall]:
    rows: list[NexusCall] = []
    physical = set(profile.states)
    if "MA" in physical or profile.incorporation_state == "MA":
        types = []
        if _has(findings, "ma.dor.excise"):
            types.append("corporate excise")
        if _has(findings, "ma.dor.saas_sales") or _has(findings, "ma.dor.sales"):
            types.append("sales/use")
        if _has_confirmed(findings, "ma.dor.meals"):
            types.append("meals")
        if _has(findings, "ma.dor.alcohol"):
            types.append("alcoholic beverages excise")
        if _has(findings, "ma.dor.property"):
            types.append("local property tax")
        if _has(findings, "ma.dor.withholding"):
            types.append("employer withholding")
        trigger = "physical presence"
        if profile.incorporation_state == "MA":
            trigger = "incorporation + physical presence"
        rows.append(
            NexusCall(
                jurisdiction="MA",
                trigger=trigger,
                nexus="YES",
                tax_types=types or ["review tax types"],
            )
        )
    for row in profile.revenue_by_state:
        if row.state in physical:
            continue
        tax = []
        if row.saas_taxable is True:
            tax.append("sales tax (if nexus)")
        elif row.saas_taxable is False:
            tax.append("SaaS often exempt — confirm")
        else:
            tax.append("sales and/or income/franchise if nexus")
        rows.append(
            NexusCall(
                jurisdiction="Other" if row.state == "OTHER" else row.state,
                trigger=f"economic — ${_money(row.amount_usd)} billed there",
                nexus="REVIEW",
                tax_types=tax,
            )
        )
    if _has(findings, "hk.ird.property_tax") or _has(findings, "hk.rvd.rates"):
        rows.append(
            NexusCall(
                jurisdiction="HK",
                trigger="Hong Kong land or buildings",
                nexus="YES",
                tax_types=["property tax", "rates"],
            )
        )
    ttb: list[str] = []
    if _has(findings, "us.fed.ttb_wine"):
        ttb.append("TTB wine excise")
    if _has(findings, "us.fed.ttb_beer"):
        ttb.append("TTB beer excise")
    if _has(findings, "us.fed.ttb_spirits"):
        ttb.append("TTB distilled spirits")
    if ttb:
        rows.append(
            NexusCall(
                jurisdiction="US",
                trigger="alcohol producer or importer",
                nexus="YES",
                tax_types=ttb,
            )
        )
    for code, rule_id, label in (
        ("AU", "au.ato.gst", "GST"),
        ("SG", "sg.iras.gst", "GST"),
        ("CA", "ca.cra.gst_hst", "GST/HST"),
        ("UK", "uk.hmrc.vat", "VAT"),
        ("CN", "cn.sta.vat", "VAT"),
        ("EU", "eu.vat.oss", "VAT/OSS"),
    ):
        if _has(findings, rule_id):
            rows.append(
                NexusCall(
                    jurisdiction=code,
                    trigger="taxable supplies on file",
                    nexus="REVIEW" if code in {"CN", "EU"} else "YES",
                    tax_types=[label],
                )
            )
    extra_local = (
        ("SG", "sg.iras.property", "property tax", "Singapore land or buildings", "YES"),
        ("UK", "uk.voa.rates", "business rates / council tax", "UK land or buildings", "REVIEW"),
        ("AU", "au.ato.land_tax", "state land tax", "Australian land", "REVIEW"),
        ("CA", "ca.prov.property", "municipal property tax", "Canadian land or buildings", "REVIEW"),
        ("CN", "cn.sta.property", "房产税 / land-use tax", "mainland real estate", "REVIEW"),
        ("HK", "hk.ced.liquor", "liquor duty", "HK liquor import or manufacture", "REVIEW"),
        ("UK", "uk.hmrc.alcohol", "alcohol duty", "UK alcohol production or import", "REVIEW"),
        ("AU", "au.ato.wet", "wine equalisation tax", "Australian wine dealing", "YES"),
        ("CA", "ca.cra.alcohol", "federal alcohol excise", "Canadian alcohol production or import", "REVIEW"),
        ("CN", "cn.sta.excise_alcohol", "消费税 (alcohol)", "mainland alcohol production or import", "REVIEW"),
        ("EU", "eu.excise.alcohol", "member-state alcohol excise", "EU alcohol release", "REVIEW"),
    )
    seen_extra: set[tuple[str, str]] = set()
    for code, rule_id, label, trigger, nexus in extra_local:
        if _has(findings, rule_id) and (code, label) not in seen_extra:
            seen_extra.add((code, label))
            rows.append(
                NexusCall(jurisdiction=code, trigger=trigger, nexus=nexus, tax_types=[label])
            )
    return rows


def _worksheet(profile: TaxProfile, findings: list[Finding]) -> list[WorksheetLine]:
    lines: list[WorksheetLine] = []
    ma = profile.state_revenue("MA")
    total = profile.total_revenue()
    if total > 0 and (ma > 0 or profile.revenue_by_state):
        factor = (ma / total) if total else Decimal("0")
        lines.append(
            WorksheetLine(
                name="MA single sales factor",
                inputs=[f"MA receipts {_money(ma)}", f"everywhere {_money(total)}"],
                result=_pct(factor),
                note="MA DOR single-sales-factor illustration. Not a return.",
                forms=["Form 355"],
            )
        )
    if _has_confirmed(findings, "ma.dor.saas_sales") and ma > 0:
        illustrated = (ma * MA_SALES_TAX).quantize(MONEY, rounding=ROUND_HALF_UP)
        freq = "monthly" if illustrated > ST9_MONTHLY_THRESHOLD else "quarterly or annual"
        lines.append(
            WorksheetLine(
                name="Illustrated MA sales tax on MA SaaS receipts",
                inputs=[f"MA receipts {_money(ma)}", f"rate {_pct(MA_SALES_TAX)}"],
                result=_money(illustrated),
                note=f"Pack rate 6.25% × MA receipts only. Filing cycle looks {freq} (monthly if annual liability exceeds $1,200).",
                forms=["ST-9"],
            )
        )
    if _has(findings, "ma.dor.excise") and profile.entity_type.value == "c_corp":
        lines.append(
            WorksheetLine(
                name="MA corporate excise floor",
                inputs=["minimum excise"],
                result=_money(MA_EXCISE_MIN),
                note="Greater of 8% of MA-apportioned net income or $2.60 per $1,000 of property/net worth, minimum $456. Net income is not in this file — accountant stops here.",
                forms=["Form 355"],
            )
        )
    if profile.payroll_usd:
        lines.append(
            WorksheetLine(
                name="Payroll in file",
                inputs=[f"gross wages {_money(profile.payroll_usd)}"],
                result=_money(profile.payroll_usd),
                note="Withholding and UI follow the employee states. No tax due is computed from this number.",
                forms=["M-941"],
            )
        )
    gst_rates = {
        "AU": (Decimal("0.10"), "au.ato.gst", "Australia GST 10%"),
        "SG": (Decimal("0.09"), "sg.iras.gst", "Singapore GST 9%"),
        "UK": (Decimal("0.20"), "uk.hmrc.vat", "UK VAT standard 20%"),
        "CA": (Decimal("0.05"), "ca.cra.gst_hst", "Canada federal GST 5% (no HST)"),
    }
    for code, (rate, rule_id, label) in gst_rates.items():
        amt = profile.gst_supplies_usd(code)
        if amt > 0 and _has(findings, rule_id):
            illustrated = (amt * rate).quantize(MONEY, rounding=ROUND_HALF_UP)
            lines.append(
                WorksheetLine(
                    name=f"Illustrated {label}",
                    inputs=[f"{code} taxable supplies {_money(amt)}", f"pack rate {_pct(rate)}"],
                    result=_money(illustrated),
                    note="Pack rate × supplies already on the file. Not a return and not a tax due.",
                    forms=["GST/VAT"],
                )
            )
    # ---- foreign account aggregation (FBAR / 8938) ----------------------
    if (_has(findings, "us.fed.fbar") or _has(findings, "us.fed.8938")) and profile.foreign_accounts:
        total_fa = profile.foreign_account_total()
        if total_fa > 0:
            verdict = "over" if total_fa > FBAR_THRESHOLD else "under"
            lines.append(
                WorksheetLine(
                    name="Foreign account aggregate (year-max balances)",
                    inputs=[f"{a.label or a.kind} {_money(a.max_balance_usd)}" for a in profile.foreign_accounts[:6]],
                    result=_money(total_fa),
                    note=f"Aggregate {verdict} the ${_money(FBAR_THRESHOLD)} FBAR threshold. Aggregate, not per-account.",
                    forms=["FBAR", "114"],
                )
            )
    # ---- foreign gift total (3520) --------------------------------------
    if _has(findings, "us.fed.3520") and profile.gifts:
        total_g = sum((g.amount_usd for g in profile.gifts), Decimal("0"))
        if total_g > 0:
            verdict = "over" if total_g > GIFT_3520_THRESHOLD else "under"
            lines.append(
                WorksheetLine(
                    name="Foreign gifts received, annual total",
                    inputs=[f"{g.source_country} gift {_money(g.amount_usd)}" for g in profile.gifts[:4]],
                    result=_money(total_g),
                    note=f"Total {verdict} the ${_money(GIFT_3520_THRESHOLD)} Form 3520 reporting threshold. The gift itself is usually not taxable; the penalty is for silence.",
                    forms=["3520"],
                )
            )
    # ---- SE tax illustration (Schedule SE) ------------------------------
    if _has_confirmed(findings, "us.fed.se_tax"):
        se_income = profile.income_total("1099_nec", "gig")
        if se_income > 0:
            base = (se_income * SE_BASE_FACTOR).quantize(MONEY, rounding=ROUND_HALF_UP)
            illustrated = (base * SE_RATE).quantize(MONEY, rounding=ROUND_HALF_UP)
            lines.append(
                WorksheetLine(
                    name="Illustrated SE tax on 1099/gig income",
                    inputs=[f"net SE income {_money(se_income)}", f"x {_pct(SE_BASE_FACTOR)} base", f"x {_pct(SE_RATE)} rate"],
                    result=_money(illustrated),
                    note=f"Pack rates on the gross already in the file — before expenses, so an upper bound. Threshold ${_money(SE_FLOOR)}.",
                    forms=["Schedule SE"],
                )
            )
    # ---- wage and tip base ----------------------------------------------
    if _has(findings, "us.fed.tips"):
        wages = profile.income_total("w2")
        tips = profile.income_total("tips")
        if tips > 0:
            monthly = (tips / Decimal("12")).quantize(MONEY, rounding=ROUND_HALF_UP)
            lines.append(
                WorksheetLine(
                    name="Wage and tip base",
                    inputs=[f"W-2 wages {_money(wages)}", f"tips {_money(tips)}"],
                    result=_money(wages + tips),
                    note=f"Tips average {_money(monthly)}/month — over the $20/month employer-reporting rule (Form 4070).",
                    forms=["4070", "W-2"],
                )
            )
    # ---- part-year day split --------------------------------------------
    move = next((e for e in profile.life_events if e.kind == "move_state" and e.date), None)
    if move and profile.part_year_states:
        try:
            from datetime import date as _date

            d = _date.fromisoformat(move.date)
            year_days = Decimal((_date(d.year, 12, 31) - _date(d.year, 1, 1)).days + 1)
            before = Decimal((d - _date(d.year, 1, 1)).days)
            frac = before / year_days
            a = move.from_state or (profile.part_year_states[0] if profile.part_year_states else "?")
            b = move.to_state or (profile.part_year_states[-1] if profile.part_year_states else "?")
            lines.append(
                WorksheetLine(
                    name="Part-year residency day split",
                    inputs=[f"moved {move.date}", f"{a}: {int(before)} days", f"{b}: {int(year_days - before)} days"],
                    result=f"{_pct(frac)} {a} / {_pct(Decimal('1') - frac)} {b}",
                    note="Day-count allocation for part-year returns. Wage sourcing follows workdays, not the calendar alone.",
                    forms=["Form 1-NR/PY"],
                )
            )
        except (ValueError, TypeError):
            pass
    # ---- MA meals tax illustration --------------------------------------
    if _has_confirmed(findings, "ma.dor.meals"):
        meals_base = profile.state_revenue("MA") or profile.income_total("sales")
        if meals_base > 0:
            state_part = (meals_base * MA_SALES_TAX).quantize(MONEY, rounding=ROUND_HALF_UP)
            local_part = (meals_base * MA_MEALS_LOCAL).quantize(MONEY, rounding=ROUND_HALF_UP)
            lines.append(
                WorksheetLine(
                    name="Illustrated MA meals tax on sales in file",
                    inputs=[f"sales {_money(meals_base)}", f"state {_pct(MA_SALES_TAX)}", f"local option {_pct(MA_MEALS_LOCAL)}"],
                    result=_money(state_part + local_part),
                    note="Pack rates x sales already in the file. POS meals-vs-merch split still needed; merch is sales-taxed, not meals-taxed.",
                    forms=["ST-9", "meals tax"],
                )
            )
    # ---- economic nexus screen ------------------------------------------
    if profile.revenue_by_state:
        physical = set(profile.states)
        rows = [r for r in profile.revenue_by_state if r.state not in physical and r.state != "OTHER"]
        if rows:
            over = [r for r in rows if r.amount_usd > MA_SALES_NEXUS]
            lines.append(
                WorksheetLine(
                    name="Economic nexus screen ($100,000 test)",
                    inputs=[f"{r.state} {_money(r.amount_usd)} — {'OVER' if r.amount_usd > MA_SALES_NEXUS else 'under'}" for r in rows[:8]],
                    result=f"{len(over)} of {len(rows)} states over",
                    note="Receipts vs the common $100,000 economic-nexus threshold. Each OVER state stays REVIEW until its statute is read.",
                    forms=["state registrations"],
                )
            )
    # ---- 83(b) statutory window -----------------------------------------
    if _has(findings, "us.fed.83b"):
        grant = next((e for e in profile.life_events if e.kind == "equity_grant" and e.date), None)
        if grant:
            try:
                from datetime import date as _date, timedelta as _td

                g = _date.fromisoformat(grant.date)
                deadline = g + _td(days=30)
                lines.append(
                    WorksheetLine(
                        name="83(b) statutory window",
                        inputs=[f"grant {grant.date}", "+ 30 days (pack)"],
                        result=deadline.isoformat(),
                        note="Statutory 30-day window, no IRS extension. A calendar problem, not a return problem.",
                        forms=["83(b)"],
                    )
                )
            except (ValueError, TypeError):
                pass
    # ---- 25% foreign-owner test (5472) ----------------------------------
    if _has(findings, "us.fed.5472") and profile.ownerships:
        pcts = [o for o in profile.ownerships if o.ownership_pct > 0 and o.entity_type == "individual"] or [
            o for o in profile.ownerships if o.ownership_pct > 0
        ]
        top = max(pcts, key=lambda o: o.ownership_pct, default=None)
        if top is not None:
            verdict = "meets" if top.ownership_pct >= FOREIGN_OWNER_5472 else "below"
            lines.append(
                WorksheetLine(
                    name="25% foreign-owner test",
                    inputs=[f"{o.name} ({o.country}) {o.ownership_pct}%" for o in pcts[:4]],
                    result=f"max {top.ownership_pct}% — {verdict} 25%",
                    note="Ownership percentages from the file vs the Form 5472 25% threshold. Reportable transactions still need the intercompany ledger.",
                    forms=["5472"],
                )
            )
    # ---- founder listed stake -------------------------------------------
    if _has(findings, "us.fed.founder_public") and profile.public_stakes:
        stake = max(profile.public_stakes, key=lambda x: x.ownership_pct)
        div = profile.income_total("dividends")
        inputs = [f"{stake.name or 'listed company'} {stake.ownership_pct}%", f"held {stake.years_held} years (>= 20 pack threshold)"]
        if div > 0:
            inputs.append(f"dividends {_money(div)}")
        lines.append(
            WorksheetLine(
                name="Concentrated founder position",
                inputs=inputs,
                result=f"{stake.ownership_pct}% of listed shares",
                note="Dividends are typically qualified; the 3.8% NIIT (pack rate) often applies. Sales, gifts, and pledges each have a different form.",
                forms=["Schedule B", "Schedule D"],
            )
        )
    if not lines:
        lines.append(
            WorksheetLine(
                name="No computable worksheet",
                inputs=[],
                result="n/a",
                note="Counsel's obligations did not include a rate the packs can apply to an amount in the profile.",
            )
        )
    return lines


def _calendar(profile: TaxProfile, findings: list[Finding]) -> list[CalendarItem]:
    items: list[CalendarItem] = []
    if _has(findings, "us.fed.1120"):
        items.append(
            CalendarItem(
                date="2026-04-15",
                jurisdiction="US",
                name="U.S. corporation income tax return",
                form="1120",
                method="IRS",
                rule_id="us.fed.1120",
            )
        )
    if _has(findings, "ma.dor.excise") and profile.entity_type.value == "c_corp":
        items.append(
            CalendarItem(
                date="2026-03-15",
                jurisdiction="MA",
                name="Corporate excise tax return",
                form="Form 355",
                rule_id="ma.dor.excise",
            )
        )
    if _has(findings, "ma.dor.355es"):
        for d, label in (
            ("2026-04-15", "Q1"),
            ("2026-06-15", "Q2"),
            ("2026-09-15", "Q3"),
            ("2027-01-15", "Q4"),
        ):
            items.append(
                CalendarItem(
                    date=d,
                    jurisdiction="MA",
                    name=f"{label} estimated corporate excise",
                    form="355-ES",
                    status="check",
                    rule_id="ma.dor.355es",
                )
            )
    if _has(findings, "ma.dor.saas_sales") or _has(findings, "ma.dor.sales") or _has(findings, "ma.dor.meals"):
        ma = profile.state_revenue("MA") or profile.income_total("sales", "saas")
        illustrated = (ma * MA_SALES_TAX) if ma else Decimal("0")
        if illustrated > ST9_MONTHLY_THRESHOLD:
            for month in range(1, 13):
                due_month = month + 1 if month < 12 else 1
                due_year = 2026 if month < 12 else 2027
                items.append(
                    CalendarItem(
                        date=f"{due_year}-{due_month:02d}-30" if due_month != 3 else f"{due_year}-03-30",
                        jurisdiction="MA",
                        name=f"Sales/meals tax period {month:02d}",
                        form="ST-9",
                        rule_id="ma.dor.saas_sales" if _has(findings, "ma.dor.saas_sales") else "ma.dor.sales",
                    )
                )
        else:
            items.append(
                CalendarItem(
                    date="2026-04-30",
                    jurisdiction="MA",
                    name="Q1 sales/meals tax",
                    form="ST-9",
                    rule_id="ma.dor.sales",
                )
            )
    if _has(findings, "ma.dor.withholding"):
        for d, label in (
            ("2026-01-31", "W-2 / M-941 recon"),
            ("2026-04-30", "Q1 withholding"),
            ("2026-07-31", "Q2 withholding"),
            ("2026-10-31", "Q3 withholding"),
            ("2027-01-31", "Q4 withholding"),
        ):
            items.append(
                CalendarItem(
                    date=d,
                    jurisdiction="MA",
                    name=label,
                    form="M-941",
                    rule_id="ma.dor.withholding",
                )
            )
    if _has(findings, "ma.dor.alcohol"):
        items.append(
            CalendarItem(
                date="2026-04-20",
                jurisdiction="MA",
                name="Alcoholic beverages excise (monthly cycle)",
                form="AB-1",
                rule_id="ma.dor.alcohol",
            )
        )
    if _has(findings, "ma.dor.property"):
        items.append(
            CalendarItem(
                date="2026-05-01",
                jurisdiction="MA",
                name="Local property tax — confirm city/town cycle",
                form="municipal tax bill",
                status="check",
                rule_id="ma.dor.property",
            )
        )
    if _has(findings, "au.ato.gst"):
        items.append(
            CalendarItem(
                date="2026-04-28",
                jurisdiction="AU",
                name="GST / WET on Business Activity Statement",
                form="BAS",
                method="ATO",
                rule_id="au.ato.gst",
            )
        )
    if _has(findings, "sg.iras.gst"):
        items.append(
            CalendarItem(
                date="2026-04-30",
                jurisdiction="SG",
                name="GST F5 (quarterly cycle)",
                form="GST F5",
                method="IRAS",
                rule_id="sg.iras.gst",
            )
        )
    if _has(findings, "uk.hmrc.vat"):
        items.append(
            CalendarItem(
                date="2026-05-07",
                jurisdiction="UK",
                name="VAT Return (one month and 7 days after quarter)",
                form="VAT Return",
                method="HMRC",
                rule_id="uk.hmrc.vat",
            )
        )
    if _has(findings, "ca.cra.gst_hst"):
        items.append(
            CalendarItem(
                date="2026-04-30",
                jurisdiction="CA",
                name="GST/HST return (assigned period)",
                form="GST34",
                method="CRA",
                rule_id="ca.cra.gst_hst",
            )
        )
    if _has(findings, "hk.ird.property_tax") or _has(findings, "hk.rvd.rates"):
        items.append(
            CalendarItem(
                date="2026-04-30",
                jurisdiction="HK",
                name="Property tax return / RVD rates demand",
                form="BIR57",
                method="IRD",
                rule_id="hk.ird.property_tax",
            )
        )
    if _has(findings, "sg.iras.property"):
        items.append(
            CalendarItem(
                date="2026-01-31",
                jurisdiction="SG",
                name="IRAS property tax",
                form="property tax",
                method="IRAS",
                rule_id="sg.iras.property",
            )
        )
    items.sort(key=lambda x: x.date)
    return items


def _counsel(profile: TaxProfile, findings: list[Finding], nexus: list[NexusCall]) -> AgencyMemo:
    yes = [n for n in nexus if n.nexus == "YES"]
    review = [n for n in nexus if n.nexus == "REVIEW"]
    required = [f.name for f in findings if f.status == FindingStatus.required]
    items = [f"{n.jurisdiction}: YES — {n.trigger}. {', '.join(n.tax_types)}." for n in yes]
    items += [f"{n.jurisdiction}: REVIEW — {n.trigger}." for n in review]
    if not items:
        items = [f"{f.jurisdiction}: {f.name} ({f.status.value})" for f in findings[:8]]
    summary = (
        f"Counsel framed {profile.display_name or profile.entity_type.value} across "
        f"{len(yes)} confirmed and {len(review)} REVIEW jurisdictions. "
        f"{len(required)} obligations look required. "
        "P.L. 86-272 and out-of-state economic nexus stay on REVIEW until a statute is checked."
    )
    return AgencyMemo(role="counsel", title="1 · Counsel — nexus and legal framework", summary=summary, items=items)


def _accountant(profile: TaxProfile, worksheet: list[WorksheetLine]) -> AgencyMemo:
    items = [f"{w.name}: {w.result} ({w.note})" for w in worksheet]
    summary = (
        "Accountant used only pack rates and amounts already in the profile. "
        "No book-to-tax, no invented net income, no 'you owe' figure."
    )
    return AgencyMemo(role="accountant", title="2a · Accountant — worksheet", summary=summary, items=items)


def _compliance(calendar: list[CalendarItem], findings: list[Finding]) -> AgencyMemo:
    docs: list[str] = []
    for f in findings:
        docs.extend(f.evidence_needed[:1])
    docs = list(dict.fromkeys(docs))[:8]
    items = [f"{c.date} · {c.jurisdiction} · {c.name} · {c.form} · {c.method}" for c in calendar[:12]]
    if len(calendar) > 12:
        items.append(f"… {len(calendar) - 12} more calendar rows")
    items += [f"Gather: {d}" for d in docs]
    summary = (
        f"Compliance built {len(calendar)} calendar rows from counsel's confirmed obligations. "
        "Nothing is marked filed. Portals stay closed."
    )
    return AgencyMemo(role="compliance", title="2b · Compliance — calendar and evidence", summary=summary, items=items)


def _review(findings: list[Finding], nexus: list[NexusCall]) -> AgencyMemo:
    blocked = [n.jurisdiction for n in nexus if n.nexus == "REVIEW"]
    blocked += [f.name for f in findings if f.status in {FindingStatus.check, FindingStatus.likely} and f.escalate]
    blocked = list(dict.fromkeys(blocked))
    ready = [f.name for f in findings if f.status == FindingStatus.required and not f.escalate]
    items = [f"Hold — {b}" for b in blocked] or ["No REVIEW holds on the nexus map."]
    items += [f"Ready for a CPA to execute — {r}" for r in ready[:6]]
    summary = (
        "Counsel review is the last legal gate. "
        "REVIEW jurisdictions and high-severity likely/check findings do not get a filing instruction. "
        "The clinic still does not file."
    )
    return AgencyMemo(role="review", title="3a · Counsel review — legal gate", summary=summary, items=items)


def run_agency(profile: TaxProfile, findings: list[Finding]) -> AgencyDocket:
    nexus = _nexus_table(profile, findings)
    worksheet = _worksheet(profile, findings)
    calendar = _calendar(profile, findings)
    return AgencyDocket(
        counsel=_counsel(profile, findings, nexus),
        accountant=_accountant(profile, worksheet),
        compliance=_compliance(calendar, findings),
        review=_review(findings, nexus),
        nexus=nexus,
        worksheet=worksheet,
        calendar=calendar,
    )

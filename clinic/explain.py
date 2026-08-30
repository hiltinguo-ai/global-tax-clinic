from __future__ import annotations

import re

from clinic.engine import pack_footer
from clinic.packs import PackMeta
from clinic.retrieve import retrieve_for
from clinic.schemas import (
    ClinicReport,
    Finding,
    FindingStatus,
    OpenQuestion,
    ReportSection,
    TaxProfile,
)

_AMOUNT = re.compile(
    r"""
    (?<![A-Za-z])
    (?:
        \$\s?\d[\d,]*(?:\.\d+)?
        | \b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b
        | \b\d+\.\d+\b
        | \b\d{4,}\b
    )
    """,
    re.VERBOSE,
)


def allowed_tokens(findings: list[Finding]) -> tuple[set[str], set[str]]:
    numbers: set[str] = set()
    forms: set[str] = set()
    for f in findings:
        forms.update(x.lower() for x in f.forms)
        forms.add(f.name.lower())
        # form numbers (3520, 8938, 1120...) are citations, not amounts
        for x in f.forms:
            if re.search(r"\d", x):
                numbers.add(_norm_num(x))
        for tok in re.findall(r"\d{3,4}(?:-[A-Z]+)?", f.name):
            numbers.add(_norm_num(tok))
        for n in f.numbers:
            numbers.add(_norm_num(n))
        for m in f.matched:
            for tok in _AMOUNT.findall(m):
                numbers.add(_norm_num(tok))
        if f.deadline and f.deadline.date and re.search(r"\d", f.deadline.date):
            numbers.add(_norm_num(f.deadline.date))
    numbers.update({"2026", "2025", "15", "30"})
    return numbers, forms


def _norm_num(n: str) -> str:
    return re.sub(r"[^\d.]", "", str(n))


def number_firewall(text: str, findings: list[Finding]) -> str:
    """Any amount not traceable to the profile or a pack threshold is redacted."""
    numbers, _ = allowed_tokens(findings)

    def repl_amt(m: re.Match) -> str:
        raw = m.group(0)
        key = _norm_num(raw)
        if key in numbers or key.rstrip("0").rstrip(".") in numbers:
            return raw
        return "[amount from findings only]"

    return _AMOUNT.sub(repl_amt, text)


_STATUS_PHRASE = {
    FindingStatus.required: "is required on the facts on file",
    FindingStatus.likely: "is likely on the facts on file",
    FindingStatus.check: "cannot be ruled in or out yet",
    FindingStatus.na: "does not apply",
}


def _profile_sketch(profile: TaxProfile) -> str:
    """One sentence describing the client from actual facts, not counts."""
    bits: list[str] = []
    if profile.us_person:
        bits.append("a US person")
    if profile.foreign_accounts:
        total = profile.foreign_account_total()
        bits.append(
            f"{len(profile.foreign_accounts)} non-US account(s)"
            + (f" with year-max balances totaling ${total:,.0f}" if total else " (balances unconfirmed)")
        )
    if profile.gifts:
        gift_total = sum(g.amount_usd for g in profile.gifts)
        bits.append(f"${gift_total:,.0f} in foreign gifts")
    if profile.income_streams:
        kinds = ", ".join(dict.fromkeys(s.kind.replace("_", "-") for s in profile.income_streams))
        bits.append(f"income from {kinds}")
    if profile.states:
        bits.append("state footprint " + "/".join(dict.fromkeys(profile.states)))
    if profile.ownerships:
        bits.append(f"ownership in {len(profile.ownerships)} foreign entit(y/ies)")
    if profile.has_founder_listed_stake:
        bits.append("a founder stake in a listed company")
    if profile.has_employees:
        bits.append("employees on payroll")
    return "; ".join(bits) if bits else "a thin file so far"


def explain(
    profile: TaxProfile,
    findings: list[Finding],
    metas: list[PackMeta],
    questions: list[OpenQuestion] | None = None,
) -> ClinicReport:
    questions = questions or []
    subject = profile.display_name or profile.entity_type.value
    sections: list[ReportSection] = []
    all_numbers: list[str] = []
    all_forms: list[str] = []

    for f in findings:
        passage_bits = []
        for p in retrieve_for(f):
            passage_bits.append(p.get("text", "").strip().split("\n")[0][:240])

        if f.confidence == "needs_facts":
            facts = "; ".join(f.matched) if f.matched else "nothing decisive yet"
            body = (
                f"{f.name} {_STATUS_PHRASE[f.status]}. "
                f"Established so far: {facts}. "
                f"One answer settles it: {f.open_questions[0] if f.open_questions else 'see the follow-up questions.'}"
            )
        else:
            facts = "; ".join(f.matched) if f.matched else f.reason
            body = f"{f.name} {_STATUS_PHRASE[f.status]} — {facts}."
            if f.explain_hints:
                body += f" {f.explain_hints[0]}"
            if f.escalate:
                body += " Discuss with a CPA before treating this as settled."

        why = " ".join(f.explain_hints[:2] + passage_bits[:1]) or f.reason
        body = number_firewall(body, findings)
        why = number_firewall(why, findings)

        next_steps = list(f.evidence_needed)
        if f.deadline:
            next_steps.append(
                f"Calendar {f.deadline.date}"
                + (f" (extends to {f.deadline.auto_extension_to})" if f.deadline.auto_extension_to else "")
                + "."
            )
        if f.confidence == "needs_facts":
            next_steps = f.open_questions + next_steps[:2]
        elif f.escalate:
            next_steps.append(f"Ask a CPA: does {f.name} apply to {subject} given the facts above?")

        sections.append(
            ReportSection(
                finding_id=f.rule_id,
                heading=f.name,
                body=body,
                why=why,
                next_steps=next_steps,
                citations=f.citations,
            )
        )
        all_numbers.extend(f.numbers)
        all_forms.extend(f.forms)

    used_ids = {f.pack_id for f in findings}
    used = [m for m in metas if m.id in used_ids]
    footer_lines = pack_footer(used or metas)
    skipped = [m.name for m in metas if m.id not in used_ids]
    states = ", ".join(dict.fromkeys(profile.states + profile.part_year_states)) or "none listed"
    skip_bit = f" Packs loaded but silent: {', '.join(skipped)}." if skipped else ""
    disclaimer = (
        f"This check-up applied {len(findings)} findings from "
        + "; ".join(footer_lines)
        + f". It did not file anything, compute a tax due, or evaluate every state (profile states: {states})."
        + skip_bit
        + " It is a clinic report, not advice and not a prepared return."
    )

    required = [f for f in findings if f.status == FindingStatus.required]
    unsettled = [f for f in findings if f.confidence == "needs_facts"]
    lede = f"{subject} — {_profile_sketch(profile)}. "
    if required:
        lede += f"{len(required)} obligation(s) are triggered outright: {', '.join(f.name for f in required[:3])}"
        lede += "…" if len(required) > 3 else ""
        lede += ". "
    if unsettled:
        lede += f"{len(unsettled)} more hinge on facts the intake did not settle — answers below would close them. "
    if not required and not unsettled:
        lede += "Nothing in the loaded packs is triggered by these facts. "
    lede += "The packs decided; the model only narrates."
    lede = number_firewall(lede, findings)

    return ClinicReport(
        title="Clinic report",
        subject=subject,
        lede=lede,
        findings=findings,
        sections=sections,
        numbers=list(dict.fromkeys(all_numbers)),
        forms=list(dict.fromkeys(all_forms)),
        packs_applied=footer_lines,
        disclaimer=disclaimer,
        open_questions=questions,
        model_versions={"extractor": "persona-or-heuristic", "explainer": "facts+firewall"},
    )

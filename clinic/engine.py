from __future__ import annotations

import re

from clinic.packs import (
    FIELD_INFO,
    Overlap,
    PackMeta,
    Rule,
    eval_trigger_report,
    load_packs,
)
from clinic.schemas import (
    Citation,
    Deadline,
    Finding,
    FindingStatus,
    OpenQuestion,
    Severity,
    TaxProfile,
)

_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
_STATUS_ORDER = {"required": 0, "likely": 1, "check": 2, "n.a.": 3}


def _forms_from_rule(rule: Rule) -> list[str]:
    if rule.forms:
        return list(rule.forms)
    forms: list[str] = []
    blob = f"{rule.id} {rule.name}".lower()
    for token in (
        "114", "FBAR", "8938", "3520", "8621", "1116", "2555", "5471", "5472",
        "1120", "1065", "83(b)", "Schedule C", "Schedule SE", "IR56B", "BIR60",
    ):
        if token.lower() in blob:
            forms.append(token)
    return forms


def _numbers_in(texts: list[str]) -> list[str]:
    """Every numeric token used in our own wording, so the firewall lets it through."""
    out: list[str] = []
    for t in texts:
        out.extend(m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", t))
    return out


def _reason_fired(rule: Rule, matched: list[str]) -> str:
    facts = "; ".join(matched) if matched else "the stated facts"
    reason = f"On these facts — {facts} — this obligation is triggered."
    if rule.explain_hints:
        reason += f" {rule.explain_hints[0]}"
    return reason


def _reason_unknown(rule: Rule, matched: list[str], missing_labels: list[str]) -> str:
    bits = []
    if matched:
        bits.append("Partly established: " + "; ".join(matched) + ".")
    bits.append(
        "Cannot be decided yet — the intake does not establish "
        + ", ".join(missing_labels)
        + "."
    )
    return " ".join(bits)


def _finding_from_rule(
    rule: Rule,
    status: FindingStatus,
    reason: str,
    matched: list[str],
    open_questions: list[str],
    confidence: str,
    profile: TaxProfile,
) -> Finding:
    severity = Severity(rule.severity)
    numbers = list(dict.fromkeys([str(n) for n in rule.numbers] + _numbers_in(matched)))
    return Finding(
        rule_id=rule.id,
        name=rule.name,
        status=status,
        severity=severity,
        jurisdiction=rule.pack.jurisdiction,
        pack_id=rule.pack.id,
        pack_version=rule.pack.version,
        tax_year=rule.pack.tax_year,
        reason=reason,
        evidence_needed=rule.evidence_needed,
        citations=[Citation(**c) for c in rule.citations],
        explain_hints=rule.explain_hints,
        deadline=Deadline(**rule.deadline) if rule.deadline else None,
        numbers=numbers,
        forms=_forms_from_rule(rule),
        escalate=severity == Severity.high and status != FindingStatus.check,
        confidence=confidence,
        matched=matched,
        open_questions=open_questions,
    )


def evaluate(
    profile: TaxProfile, packs_root=None, pack_ids: list[str] | None = None
) -> tuple[list[Finding], list[PackMeta]]:
    findings, metas, _ = evaluate_detailed(profile, packs_root=packs_root, pack_ids=pack_ids)
    return findings, metas


def evaluate_detailed(
    profile: TaxProfile, packs_root=None, pack_ids: list[str] | None = None
) -> tuple[list[Finding], list[PackMeta], list[OpenQuestion]]:
    rules, overlaps, metas = load_packs(packs_root)
    if pack_ids:
        allowed = set(pack_ids)
        rules = [r for r in rules if r.pack.id in allowed]
        metas = [m for m in metas if m.id in allowed]

    # Empty facts_provided = profile built directly (tests, gold personas):
    # classic two-valued evaluation, nothing is "unknown".
    known = set(profile.facts_provided) if profile.facts_provided else None

    findings: list[Finding] = []
    near_misses: list[Finding] = []
    fired: set[str] = set()
    q_by_field: dict[str, OpenQuestion] = {}

    for rule in rules:
        if rule.applies_to and not (set(rule.applies_to) & set(profile.types_on_file())):
            continue
        rep = eval_trigger_report(profile, rule.trigger, known)

        if rep.value is True:
            fired.add(rule.id)
            findings.append(
                _finding_from_rule(
                    rule,
                    FindingStatus(rule.status_if_true),
                    _reason_fired(rule, rep.matched),
                    rep.matched,
                    [],
                    "confirmed",
                    profile,
                )
            )
            continue

        if rep.value is None:
            labels, questions = [], []
            for f in rep.missing:
                label, question = FIELD_INFO.get(f, (f.replace("_", " "), f"Please confirm {f.replace('_', ' ')}."))
                labels.append(label)
                questions.append(question)
                q = q_by_field.get(f)
                if q is None:
                    q_by_field[f] = OpenQuestion(
                        field=f, question=question, severity=rule.severity, rules=[rule.name]
                    )
                else:
                    if rule.name not in q.rules:
                        q.rules.append(rule.name)
                    if _SEV_ORDER[rule.severity] < _SEV_ORDER[q.severity]:
                        q.severity = rule.severity
            # only high-severity near-misses surface as findings; the rest
            # stay as follow-up questions so the report is not flooded
            if rule.severity == "high":
                near_misses.append(
                    _finding_from_rule(
                        rule,
                        FindingStatus.check,
                        _reason_unknown(rule, rep.matched, labels),
                        rep.matched,
                        questions,
                        "needs_facts",
                        profile,
                    )
                )

    # the near-misses closest to firing (most conditions already met) first
    near_misses.sort(key=lambda f: (-len(f.matched), f.name))
    findings.extend(near_misses[:6])

    for overlap in overlaps:
        matched = _overlap_hits(overlap, fired)
        if len(matched) < 2:
            continue
        findings.append(_overlap_finding(overlap, matched, metas))
        for f in findings:
            if f.rule_id in matched:
                f.paired_with = [x for x in matched if x != f.rule_id] + [overlap.id]

    findings.sort(
        key=lambda f: (_SEV_ORDER[f.severity.value], _STATUS_ORDER[f.status.value], f.name)
    )
    questions = sorted(q_by_field.values(), key=lambda q: (_SEV_ORDER[q.severity], q.field))[:8]
    return findings, metas, questions


def _overlap_hits(overlap: Overlap, fired: set[str]) -> list[str]:
    hits: list[str] = []
    for pair in overlap.pairs:
        if pair in fired:
            hits.append(pair)
        elif pair.endswith(".*"):
            prefix = pair[:-1]
            hits.extend(sorted(r for r in fired if r.startswith(prefix)))
    return list(dict.fromkeys(hits))


def _overlap_finding(overlap: Overlap, matched: list[str], metas: list[PackMeta]) -> Finding:
    pack = next((m for m in metas if m.id == "cross-border"), metas[0] if metas else None)
    return Finding(
        rule_id=overlap.id,
        name=overlap.name,
        status=FindingStatus.likely,
        severity=Severity(overlap.severity),
        jurisdiction="cross-border",
        pack_id="cross-border",
        pack_version=pack.version if pack else "0.1",
        tax_year=pack.tax_year if pack else "",
        reason=overlap.note + " Paired rules: " + ", ".join(matched) + ".",
        citations=[Citation(**c) for c in overlap.citations],
        explain_hints=[overlap.note],
        paired_with=matched,
        forms=[],
        numbers=[],
        escalate=overlap.severity == "high",
        matched=[f"both sides of the overlap fired: {', '.join(matched)}"],
    )


def pack_footer(metas: list[PackMeta]) -> list[str]:
    return [
        f"{m.name} {m.tax_year} v{m.version} (reviewed {m.last_reviewed_on} by {m.last_reviewed_by})"
        for m in metas
    ]

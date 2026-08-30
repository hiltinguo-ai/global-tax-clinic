from __future__ import annotations

import ast
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from clinic.schemas import TaxProfile

ROOT = Path(__file__).resolve().parent.parent
PACKS_DIR = ROOT / "packs"


class PackError(ValueError):
    pass


@dataclass
class PackMeta:
    id: str
    name: str
    jurisdiction: str
    tax_year: str
    version: str
    effective_from: str
    last_reviewed_by: str
    last_reviewed_on: str
    path: Path


@dataclass
class Rule:
    id: str
    name: str
    applies_to: list[str]
    trigger: dict[str, Any]
    severity: str
    status_if_true: str
    deadline: dict[str, Any] | None
    evidence_needed: list[str]
    citations: list[dict[str, str]]
    explain_hints: list[str]
    forms: list[str]
    numbers: list[str]
    cross_border: dict[str, Any] | None
    pack: PackMeta
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Overlap:
    id: str
    name: str
    pairs: list[str]
    note: str
    severity: str
    citations: list[dict[str, str]]


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_packs(root: Path | None = None) -> tuple[list[Rule], list[Overlap], list[PackMeta]]:
    root = root or PACKS_DIR
    rules: list[Rule] = []
    metas: list[PackMeta] = []
    for pack_yaml in sorted(root.glob("**/pack.yaml")):
        data = _load_yaml(pack_yaml) or {}
        meta = PackMeta(
            id=data["id"],
            name=data.get("name", data["id"]),
            jurisdiction=data.get("jurisdiction", data["id"]),
            tax_year=str(data.get("tax_year", "")),
            version=str(data.get("version", "0.1")),
            effective_from=str(data.get("effective_from", "")),
            last_reviewed_by=data.get("last_reviewed_by", ""),
            last_reviewed_on=str(data.get("last_reviewed_on", "")),
            path=pack_yaml.parent,
        )
        metas.append(meta)
        rules_dir = pack_yaml.parent / "rules"
        if not rules_dir.is_dir():
            continue
        for rule_path in sorted(rules_dir.glob("*.yaml")):
            raw = _load_yaml(rule_path) or {}
            rules.append(
                Rule(
                    id=raw["id"],
                    name=raw["name"],
                    applies_to=list(raw.get("applies_to") or []),
                    trigger=raw.get("trigger") or {},
                    severity=raw.get("severity", "medium"),
                    status_if_true=raw.get("status_if_true", "required"),
                    deadline=raw.get("deadline"),
                    evidence_needed=list(raw.get("evidence_needed") or []),
                    citations=list(raw.get("citations") or []),
                    explain_hints=list(raw.get("explain_hints") or []),
                    forms=list(raw.get("forms") or []),
                    numbers=[str(n) for n in (raw.get("numbers") or [])],
                    cross_border=raw.get("cross_border"),
                    pack=meta,
                    raw=raw,
                )
            )
    overlaps: list[Overlap] = []
    overlap_path = root / "cross-border" / "overlaps.yaml"
    if overlap_path.exists():
        payload = _load_yaml(overlap_path) or {}
        for item in payload.get("overlaps") or []:
            overlaps.append(
                Overlap(
                    id=item["id"],
                    name=item["name"],
                    pairs=list(item.get("pairs") or []),
                    note=item.get("note", ""),
                    severity=item.get("severity", "medium"),
                    citations=list(item.get("citations") or []),
                )
            )
    return rules, overlaps, metas


def _get_path(profile: TaxProfile, path: str) -> Any:
    cur: Any = profile
    for part in path.split("."):
        if part == "profile":
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return Decimal(str(value))


def _eval_cmp(left: Any, op: str, right: Any) -> bool:
    if op == "==":
        if isinstance(right, bool) or isinstance(left, bool):
            return bool(left) is bool(right) if not isinstance(left, str) else left == right
        return left == right
    if op == "!=":
        return left != right
    if op in {">", ">=", "<", "<="}:
        l, r = _as_decimal(left), _as_decimal(right)
        return {">": l > r, ">=": l >= r, "<": l < r, "<=": l <= r}[op]
    raise PackError(f"unsupported operator {op}")


def _eval_sum(profile: TaxProfile, collection: str, field_name: str) -> Decimal:
    items = _get_path(profile, collection) or []
    total = Decimal("0")
    for item in items:
        total += _as_decimal(getattr(item, field_name, 0))
    return total


def _eval_any(profile: TaxProfile, collection: str, field_name: str, op: str, right: Any) -> bool:
    items = _get_path(profile, collection) or []
    for item in items:
        left = getattr(item, field_name, None) if not isinstance(item, dict) else item.get(field_name)
        if _eval_cmp(left, op, right):
            return True
    return False


def _eval_count(profile: TaxProfile, collection: str) -> int:
    items = _get_path(profile, collection) or []
    return len(list(items))


def _eval_expr(profile: TaxProfile, expr: str) -> bool:
    """Evaluate a tiny boolean expression against the profile.

    Supported:
      profile.us_person == true
      profile.entity_type == "llc"
      profile.dependents >= 1
      "MA" in profile.part_year_states
      sum(profile.foreign_accounts[*].max_balance_usd) > 10000
      any(profile.foreign_accounts[*].kind == "fund")
      count(profile.gifts) >= 1
      profile.has_income("1099_nec", "tips")
    """
    expr = expr.strip()
    if expr.startswith("sum(") and expr.endswith(")"):
        raise PackError("sum() must be used in a comparison")

    # membership: "MA" in profile.part_year_states
    if " in " in expr and not expr.startswith("any("):
        left, right = expr.split(" in ", 1)
        needle = ast.literal_eval(left.strip())
        hay = _get_path(profile, right.strip()) or []
        return needle in hay

    if expr.startswith("has_income(") or expr.startswith("profile.has_income("):
        inner = expr[expr.index("(") + 1 : expr.rindex(")")]
        kinds = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
        return profile.has_income(*kinds)

    if expr.startswith("has_property(") or expr.startswith("profile.has_property("):
        inner = expr[expr.index("(") + 1 : expr.rindex(")")]
        keys = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
        return profile.has_property(*keys)

    if expr.startswith("has_alcohol(") or expr.startswith("profile.has_alcohol("):
        inner = expr[expr.index("(") + 1 : expr.rindex(")")]
        keys = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
        return profile.has_alcohol(*keys)

    if expr.startswith("has_gst(") or expr.startswith("profile.has_gst("):
        inner = expr[expr.index("(") + 1 : expr.rindex(")")]
        keys = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
        return profile.has_gst(*keys)

    if expr.startswith("alcohol_match(") or expr.startswith("profile.alcohol_match("):
        inner = expr[expr.index("(") + 1 : expr.rindex(")")]
        keys = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
        return profile.alcohol_match(str(keys[0]), *keys[1:]) if keys else False

    if expr.startswith("state_revenue(") or expr.startswith("profile.state_revenue("):
        # state_revenue("MA") > 100000
        start = expr.index("(") + 1
        end = expr.index(")")
        state = ast.literal_eval(expr[start:end].strip())
        rest = expr[end + 1 :].strip()
        _, (op, right) = _split_cmp("x " + rest)
        return _eval_cmp(profile.state_revenue(str(state)), op, right)

    if expr.startswith("any("):
        inner = expr[4:-1]
        # any(profile.foreign_accounts[*].kind == "fund")
        path_part, cmp_part = _split_cmp(inner)
        collection, field_name = _star_path(path_part)
        op, right = cmp_part
        return _eval_any(profile, collection, field_name, op, right)

    if expr.startswith("count("):
        inner, op, right = _split_leading_fn(expr, "count")
        collection = inner.replace("[*]", "").strip()
        return _eval_cmp(_eval_count(profile, collection), op, right)

    if expr.startswith("sum("):
        inner, op, right = _split_leading_fn(expr, "sum")
        collection, field_name = _star_path(inner)
        return _eval_cmp(_eval_sum(profile, collection, field_name), op, right)

    path, (op, right) = _split_cmp(expr)
    left = _get_path(profile, path)
    if isinstance(left, Decimal) and not isinstance(right, bool):
        right = _as_decimal(right)
    return _eval_cmp(left, op, right)


def _star_path(path: str) -> tuple[str, str]:
    # profile.foreign_accounts[*].max_balance_usd
    if "[*]" not in path:
        raise PackError(f"expected [*] in {path}")
    collection, field_name = path.split("[*].", 1)
    return collection.strip(), field_name.strip()


def _split_cmp(expr: str) -> tuple[str, tuple[str, Any]]:
    for op in (">=", "<=", "!=", "==", ">", "<"):
        if op in expr:
            left, right = expr.split(op, 1)
            return left.strip(), (op, _parse_literal(right.strip()))
    raise PackError(f"no comparison in {expr!r}")


def _split_leading_fn(expr: str, name: str) -> tuple[str, str, Any]:
    # sum(...) > 10000
    assert expr.startswith(f"{name}(")
    depth = 0
    end = None
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise PackError(f"unbalanced {name}()")
    inner = expr[len(name) + 1 : end]
    rest = expr[end + 1 :].strip()
    path, (op, right) = _split_cmp("x " + rest)  # dummy left
    return inner, op, right


def _parse_literal(token: str) -> Any:
    low = token.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null" or low == "none":
        return None
    try:
        return ast.literal_eval(token)
    except (ValueError, SyntaxError):
        return token.strip("'\"")


def eval_trigger(profile: TaxProfile, trigger: dict[str, Any]) -> bool:
    if not trigger:
        return False
    if "all" in trigger:
        return all(_eval_clause(profile, c) for c in trigger["all"])
    if "any" in trigger:
        return any(_eval_clause(profile, c) for c in trigger["any"])
    if "not" in trigger:
        return not _eval_clause(profile, trigger["not"])
    raise PackError(f"trigger must be all/any/not, got {trigger!r}")


def _eval_clause(profile: TaxProfile, clause: Any) -> bool:
    if isinstance(clause, str):
        return _eval_expr(profile, clause)
    if isinstance(clause, dict):
        return eval_trigger(profile, clause)
    raise PackError(f"bad clause {clause!r}")


# ---------------------------------------------------------------------------
# Three-valued trigger evaluation: true / false / unknown.
#
# A live intake never states every field. When a clause depends on a field the
# intake did not establish, the honest answer is "unknown", not "false" —
# unknown rules become follow-up questions instead of silent misses.
# Profiles with an empty facts_provided (tests, gold personas built directly)
# keep the classic two-valued behavior.
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass


FIELD_INFO: dict[str, tuple[str, str]] = {
    "us_person": (
        "US-person status",
        "Are you a US person (citizen, green-card holder, or substantial presence)?",
    ),
    "residencies": ("tax residencies", "Which countries are you tax-resident in?"),
    "states": ("US state footprint", "Which US states do you live or operate in?"),
    "part_year_states": ("part-year state moves", "Did you move between US states during the year?"),
    "days_in_cn": ("days in mainland China", "How many days did you spend in mainland China this year?"),
    "dependents": ("dependents", "Do you have children or other dependents?"),
    "foreign_accounts": (
        "non-US financial accounts",
        "Do you hold any non-US bank, brokerage, retirement (e.g. MPF), or fund accounts — and what was each one's maximum balance this year?",
    ),
    "income_streams": (
        "income sources",
        "What income did you have this year (W-2, tips, 1099/gig, rental, RSUs, sales)?",
    ),
    "ownerships": ("foreign entity ownership", "Do you own 10% or more of any non-US company?"),
    "gifts": (
        "foreign gifts",
        "Did you receive gifts or bequests from a non-US person this year, and roughly how much in total?",
    ),
    "life_events": ("life events", "Any equity grants, moves, births, or new entities this year?"),
    "has_restaurant": ("restaurant operations", "Does the business serve prepared food or meals?"),
    "has_employees": ("employees", "Does the business have employees on payroll?"),
    "chinese_founders": ("founder nationality", "Are any founders Chinese tax residents?"),
    "industry": ("industry", "What does the business sell (SaaS, restaurant, goods, services)?"),
    "incorporation_state": ("incorporation state", "Which state is the entity incorporated in?"),
    "revenue_by_state": ("revenue by state", "Roughly how much revenue comes from each US state?"),
    "employee_states": ("employee locations", "Which states are your employees based in?"),
    "payroll_usd": ("payroll", "What is the approximate annual payroll?"),
    "public_stakes": (
        "founder stock",
        "Do you still hold founder stock in a listed company, and what percentage?",
    ),
    "properties": (
        "real property",
        "Do you own or rent out real estate, and in which state or country?",
    ),
    "alcohol": (
        "wine or alcohol",
        "Do you produce, import, or sell wine, beer, or spirits, and under what license?",
    ),
    "gst_supplies": (
        "GST / VAT supplies",
        "Do you make taxable supplies in a GST/VAT country (AU, SG, CA, UK, EU, CN), and are you registered?",
    ),
    "entity_type": ("entity type", "Is the primary client an individual, LLC, C-corp, or trust?"),
    "has_family_trust": (
        "family trust",
        "Is there a family trust on this file (even if the primary client is the individual settlor or beneficiary)?",
    ),
    "filing_status": ("filing status", "What is your filing status (single, MFJ, ...)?"),
    "income_band": ("income band", "Roughly which income band applies — high-net-worth, middle, or lower income?"),
}

# computed properties resolve to the source fields the intake can actually provide
_COMPUTED_SOURCES: dict[str, list[str]] = {
    "has_founder_listed_stake": ["public_stakes"],
    "founder_listed_years": ["public_stakes"],
    "founder_foreign_listed_pct": ["public_stakes"],
    "out_of_state_revenue_count": ["revenue_by_state"],
    "foreign_account_total": ["foreign_accounts"],
    "has_property": ["properties"],
    "has_alcohol": ["alcohol"],
    "alcohol_match": ["alcohol"],
    "has_gst": ["gst_supplies"],
    "gst_supplies_usd": ["gst_supplies"],
}

import re as _re


def fields_in_clause(expr: str) -> set[str]:
    """Profile fields a leaf expression depends on."""
    fields: set[str] = set()
    for m in _re.finditer(r"profile\.([a-z_0-9]+)", expr):
        name = m.group(1)
        fields.update(_COMPUTED_SOURCES.get(name, [name]))
    if "has_income(" in expr:
        fields.add("income_streams")
    if "state_revenue(" in expr:
        fields.add("revenue_by_state")
    if "has_property(" in expr:
        fields.add("properties")
    if "has_alcohol(" in expr or "alcohol_match(" in expr:
        fields.add("alcohol")
    if "has_gst(" in expr:
        fields.add("gst_supplies")
    fields.discard("has_income")
    fields.discard("state_revenue")
    fields.discard("has_property")
    fields.discard("has_alcohol")
    fields.discard("alcohol_match")
    fields.discard("has_gst")
    return fields


def _fmt_val(v: Any) -> str:
    import enum as _enum

    if isinstance(v, _enum.Enum):
        v = v.value
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, Decimal):
        return f"${v:,.0f}" if v == v.to_integral_value() else f"${v:,.2f}"
    if isinstance(v, (int, float)):
        return f"{v:,}"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or "none"
    return str(v)


def _label(path: str) -> str:
    name = path.split(".")[-1].replace("[*]", "")
    for f in fields_in_clause(path if path.startswith("profile.") else f"profile.{name}"):
        if f in FIELD_INFO:
            return FIELD_INFO[f][0]
    return name.replace("_", " ")


def describe_clause(profile: TaxProfile, expr: str) -> str:
    """Human-readable statement of why a satisfied leaf clause is satisfied."""
    expr = expr.strip()
    try:
        if " in " in expr and not expr.startswith("any("):
            left, right = expr.split(" in ", 1)
            needle = ast.literal_eval(left.strip())
            return f"{needle} is one of the client's {_label(right.strip())}"
        if "has_income(" in expr:
            inner = expr[expr.index("(") + 1 : expr.rindex(")")]
            kinds = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
            have = [s.kind for s in profile.income_of(*kinds)]
            return f"income includes {', '.join(dict.fromkeys(have)) or '/'.join(kinds)}"
        if "has_property(" in expr:
            inner = expr[expr.index("(") + 1 : expr.rindex(")")]
            keys = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
            where = ", ".join(f"{p.country}{('/' + p.state) if p.state else ''}" for p in profile.properties)
            return f"real property on file" + (f" in {', '.join(keys)}" if keys else "") + (f" ({where})" if where else "")
        if "alcohol_match(" in expr or "has_alcohol(" in expr:
            inner = expr[expr.index("(") + 1 : expr.rindex(")")]
            keys = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
            have = [f"{a.kind}/{a.role}" for a in profile.alcohol]
            return f"alcohol on file: {', '.join(have) or 'yes'}" + (f" matching {', '.join(keys)}" if keys else "")
        if "has_gst(" in expr:
            inner = expr[expr.index("(") + 1 : expr.rindex(")")]
            keys = [ast.literal_eval(p.strip()) for p in inner.split(",") if p.strip()]
            have = [g.country for g in profile.gst_supplies]
            return f"GST/VAT supplies in {', '.join(have) or 'file'}" + (f" (looking for {', '.join(keys)})" if keys else "")
        if "state_revenue(" in expr:
            start = expr.index("(") + 1
            end = expr.index(")")
            state = ast.literal_eval(expr[start:end].strip())
            rest = expr[end + 1 :].strip()
            _, (op, right) = _split_cmp("x " + rest)
            val = profile.state_revenue(str(state))
            return f"{state} revenue {_fmt_val(val)} {op} {_fmt_val(_as_decimal(right))}"
        if expr.startswith("any("):
            inner = expr[4:-1]
            path_part, (op, right) = _split_cmp(inner)
            collection, field_name = _star_path(path_part)
            return f"at least one of the {_label(collection)} has {field_name.replace('_', ' ')} {op} {_fmt_val(right)}"
        if expr.startswith("count("):
            inner, op, right = _split_leading_fn(expr, "count")
            collection = inner.replace("[*]", "").strip()
            n = _eval_count(profile, collection)
            return f"{n} {_label(collection)} on file ({op} {right} needed)"
        if expr.startswith("sum("):
            inner, op, right = _split_leading_fn(expr, "sum")
            collection, field_name = _star_path(inner)
            total = _eval_sum(profile, collection, field_name)
            return f"{_label(collection)} total {_fmt_val(total)}, {op} the {_fmt_val(_as_decimal(right))} threshold"
        path, (op, right) = _split_cmp(expr)
        left = _get_path(profile, path)
        if op == "==" and isinstance(right, bool):
            return f"{_label(path)}: {_fmt_val(left)}"
        if op == "==":
            return f"{_label(path)} is {_fmt_val(left)}"
        return f"{_label(path)} {_fmt_val(left)} {op} {_fmt_val(right)}"
    except Exception:
        return expr


@_dataclass
class TriggerReport:
    value: bool | None  # None = cannot be decided from the facts provided
    matched: list[str]  # satisfied conditions, human-readable, with real values
    missing: list[str]  # profile fields that are unknown and decisive


def _clause_report(profile: TaxProfile, clause: Any, known: set[str] | None) -> TriggerReport:
    if isinstance(clause, dict):
        return eval_trigger_report(profile, clause, known)
    expr = str(clause)
    needed = fields_in_clause(expr)
    if known is not None:
        unknown = {f for f in needed if f not in known}
        if unknown:
            return TriggerReport(None, [], sorted(unknown))
    value = _eval_expr(profile, expr)
    return TriggerReport(bool(value), [describe_clause(profile, expr)] if value else [], [])


def eval_trigger_report(
    profile: TaxProfile, trigger: dict[str, Any], known: set[str] | None = None
) -> TriggerReport:
    """Kleene-style evaluation. known=None keeps the classic two-valued path."""
    if not trigger:
        return TriggerReport(False, [], [])
    if "all" in trigger:
        reports = [_clause_report(profile, c, known) for c in trigger["all"]]
        if any(r.value is False for r in reports):
            return TriggerReport(False, [], [])
        matched = [m for r in reports for m in r.matched]
        if any(r.value is None for r in reports):
            missing = sorted({f for r in reports if r.value is None for f in r.missing})
            return TriggerReport(None, matched, missing)
        return TriggerReport(True, matched, [])
    if "any" in trigger:
        reports = [_clause_report(profile, c, known) for c in trigger["any"]]
        for r in reports:
            if r.value is True:
                return TriggerReport(True, r.matched, [])
        if any(r.value is None for r in reports):
            missing = sorted({f for r in reports if r.value is None for f in r.missing})
            return TriggerReport(None, [], missing)
        return TriggerReport(False, [], [])
    if "not" in trigger:
        r = _clause_report(profile, trigger["not"], known)
        if r.value is None:
            return TriggerReport(None, [], r.missing)
        if r.value:
            return TriggerReport(False, [], [])
        return TriggerReport(True, [f"not the case that: {trigger['not']}"], [])
    raise PackError(f"trigger must be all/any/not, got {trigger!r}")

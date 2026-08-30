from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from pydantic import BaseModel


class ModelClient:
    """Single door for model calls. Schema-constrained. No free text to the UI.

    Host resolution: OLLAMA_HOST env var, else localhost. Availability is
    checked once per client instance so a request doesn't ping Ollama three
    times; generation gets a real timeout and one retry.
    """

    def __init__(self, host: str | None = None, timeout: float = 45.0) -> None:
        host = host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        if not host.startswith("http"):
            host = f"http://{host}"
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._models: list[str] | None = None  # None = not checked yet

    def available(self) -> bool:
        return bool(self.list_models())

    def list_models(self) -> list[str]:
        if self._models is not None:
            return self._models
        if os.environ.get("CLINIC_NO_MODEL") == "1":
            self._models = []
            return self._models
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=1.5)
            r.raise_for_status()
            self._models = [
                _norm_name(m.get("name", ""))
                for m in r.json().get("models", [])
                if m.get("name")
            ]
        except httpx.HTTPError:
            self._models = []
        return self._models

    def generate_json(
        self,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.available():
            return None
        payload = {
            "model": model,
            "stream": False,
            "format": schema,
            "think": False,  # Qwen 3.5 thinks by default; clinic calls need JSON, not a trace
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            r = httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "")
            data = json.loads(content)
            if isinstance(data, dict):
                return data
        except (httpx.HTTPError, json.JSONDecodeError, TypeError):
            return None
        return None


def _norm_name(name: str) -> str:
    return name[:-7] if name.endswith(":latest") else name


def schema_of(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()


# Two desks. Qwen handles CJK / HK / CN intake. Phi handles English US-tax narration.
# Either role falls back to the other if only one model is installed.
BILINGUAL_PREFER = (
    "qwen3.5:4b", "qwen3:4b", "qwen2.5:7b", "qwen2.5:3b",
)
US_TAX_PREFER = (
    "phi5-mini", "phi4-mini", "phi4:mini", "phi4",
    "gemma4:e4b", "gemma3:4b", "ministral",
)
# kept so older callers that still say EXTRACT_PREFER / ANALYZE_PREFER keep working
EXTRACT_PREFER = BILINGUAL_PREFER + US_TAX_PREFER
ANALYZE_PREFER = US_TAX_PREFER + BILINGUAL_PREFER

_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_BILINGUAL_HINTS = (
    "hong kong", "hongkong", "mainland china", "china mainland",
    "people's republic", "simplified chinese", "traditional chinese",
    "人民币", "港币", "国内", "中国", "香港", "台灣", "台湾",
)


def pick_models(client: ModelClient | None) -> dict[str, str | None]:
    empty = {"extract": None, "analyze": None, "bilingual": None, "us_tax": None}
    if client is None or not client.available():
        return empty
    names = client.list_models()
    bilingual = _first_match(names, BILINGUAL_PREFER)
    us_tax = _first_match(names, US_TAX_PREFER)
    leftover = _first_usable(names)
    bilingual = bilingual or us_tax or leftover
    us_tax = us_tax or bilingual
    return {
        "extract": bilingual or us_tax,
        "analyze": us_tax or bilingual,
        "bilingual": bilingual,
        "us_tax": us_tax,
    }


def intake_wants_bilingual(text: str) -> bool:
    raw = text or ""
    if _CJK.search(raw):
        return True
    low = raw.lower()
    return any(h in low for h in _BILINGUAL_HINTS)


def analyze_wants_bilingual(profile: Any, findings: list[Any] | None = None) -> bool:
    residencies = {str(r).upper() for r in getattr(profile, "residencies", None) or []}
    if residencies & {"CN", "HK", "TW"}:
        return True
    for f in findings or []:
        pack = str(getattr(f, "pack_id", "") or "")
        rule = str(getattr(f, "rule_id", "") or "")
        if pack in {"cn-sta", "hk-ird"} or rule.startswith(("cn.", "hk.")):
            return True
    return False


def route_extract(client: ModelClient | None, text: str) -> str | None:
    picked = pick_models(client)
    if intake_wants_bilingual(text):
        return picked.get("bilingual") or picked.get("us_tax")
    return picked.get("us_tax") or picked.get("bilingual")


def route_analyze(
    client: ModelClient | None,
    profile: Any,
    findings: list[Any] | None = None,
) -> str | None:
    picked = pick_models(client)
    if analyze_wants_bilingual(profile, findings):
        return picked.get("bilingual") or picked.get("us_tax")
    return picked.get("us_tax") or picked.get("bilingual")


def _first_match(installed: list[str], preferred: tuple[str, ...]) -> str | None:
    lower = [n.lower() for n in installed]
    for want in preferred:
        for raw, low in zip(installed, lower):
            if want in low:
                return raw
    return None


def _first_usable(installed: list[str]) -> str | None:
    usable = [n for n in installed if "embed" not in n.lower() and "bge" not in n.lower()]
    return usable[0] if usable else None

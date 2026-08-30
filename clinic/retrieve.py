from __future__ import annotations

import json
from pathlib import Path

from clinic.schemas import Finding

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "sources"


def load_passages() -> list[dict]:
    passages: list[dict] = []
    index = SOURCES_DIR / "index.json"
    if index.exists():
        passages.extend(json.loads(index.read_text(encoding="utf-8")))
        return passages
    for path in sorted(SOURCES_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        passages.append({"id": path.stem, "title": path.stem, "text": text, "path": str(path)})
    return passages


def retrieve_for(finding: Finding, passages: list[dict] | None = None, limit: int = 2) -> list[dict]:
    passages = passages if passages is not None else load_passages()
    wanted = {c.passage_id for c in finding.citations if c.passage_id}
    hits = [p for p in passages if p.get("id") in wanted]
    if hits:
        return hits[:limit]
    tokens = set((finding.rule_id + " " + finding.name).lower().split())
    scored: list[tuple[int, dict]] = []
    for p in passages:
        blob = (p.get("title", "") + " " + p.get("text", "")).lower()
        score = sum(1 for t in tokens if len(t) > 3 and t in blob)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:limit]]

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from clinic.extract import extract
from clinic.models import ModelClient, pick_models
from clinic.personas import list_personas
from clinic.schemas import CheckupResponse, EntityType, IncomeBand, IntakeRequest, TaxProfile
from clinic.visit import run_visit

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="AiriTax - the Global Tax Clinic", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    client = ModelClient()
    models = pick_models(client)
    return {"ok": True, "live": True, "ollama": client.available(), "models": models}


@app.get("/api/personas")
def personas() -> list[dict]:
    return list_personas()


@app.post("/api/extract", response_model=TaxProfile)
def api_extract(req: IntakeRequest) -> TaxProfile:
    profile, _ = extract(req.text, persona_id=req.persona_id, client=ModelClient(), live=req.live)
    return profile


@app.post("/api/checkup", response_model=CheckupResponse)
def checkup(req: IntakeRequest) -> CheckupResponse:
    return run_visit(
        text=req.text,
        persona_id=req.persona_id,
        live=req.live,
        entity_type=req.entity_type,
        income_band=req.income_band,
        has_family_trust=req.has_family_trust,
        consider_property=req.consider_property,
        consider_alcohol=req.consider_alcohol,
        consider_gst=req.consider_gst,
        jurisdictions=req.jurisdictions,
    )


@app.post("/api/engage", response_model=CheckupResponse)
async def engage(
    text: str = Form(""),
    persona_id: str = Form(""),
    entity_type: str = Form(""),
    income_band: str = Form(""),
    jurisdictions: str = Form("[]"),
    live: bool = Form(True),
    founder_listed: bool = Form(False),
    has_family_trust: bool = Form(False),
    consider_property: bool = Form(False),
    consider_alcohol: bool = Form(False),
    consider_gst: bool = Form(False),
    files: list[UploadFile] | None = File(None),
) -> CheckupResponse:
    uploaded: list[tuple[str, bytes]] = []
    for item in files or []:
        if not item.filename:
            continue
        uploaded.append((item.filename, await item.read()))
    try:
        jur = json.loads(jurisdictions) if jurisdictions else []
    except json.JSONDecodeError:
        jur = [p.strip() for p in jurisdictions.split(",") if p.strip()]
    return await run_in_threadpool(
        run_visit,
        text=text,
        persona_id=persona_id or None,
        live=live,
        entity_type=EntityType(entity_type) if entity_type in EntityType._value2member_map_ else None,
        income_band=IncomeBand(income_band) if income_band in IncomeBand._value2member_map_ else None,
        jurisdictions=jur,
        files=uploaded,
        founder_listed=founder_listed,
        has_family_trust=has_family_trust,
        consider_property=consider_property,
        consider_alcohol=consider_alcohol,
        consider_gst=consider_gst,
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

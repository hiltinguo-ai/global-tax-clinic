import io
import zipfile
from pathlib import Path

from clinic.layers import pack_ids_for
from clinic.schemas import EntityType, IncomeBand
from clinic.visit import run_visit

DEMO = Path(__file__).resolve().parents[2] / "demo_docs"


def test_three_layers_on_nimbus():
    out = run_visit(
        text="NimbusFlow Massachusetts C-corp SaaS",
        persona_id="nimbus",
        entity_type=None,
        jurisdictions=["us-federal", "massachusetts", "other-us-states"],
    )
    assert out.layers is not None
    assert "C corporation" in out.layers.engagement.who
    assert out.layers.engagement.recommendations
    assert out.layers.analysis.rulings_applied
    assert out.layers.workpapers.steps
    assert any("355" in s.name or "saas" in s.rule_id for s in out.layers.workpapers.steps)


def test_jurisdiction_filter_drops_hk_for_nimbus():
    out = run_visit(
        text="",
        persona_id="nimbus",
        jurisdictions=["massachusetts"],
    )
    ids = {f.pack_id for f in out.findings}
    assert "hk-ird" not in ids
    assert "us-state-ma" in ids


def test_zip_upload_feeds_layer1_documents():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "notes.txt",
            "Sichuan Garden is a Massachusetts LLC restaurant with employees and meals sales.",
        )
    out = run_visit(
        text="",
        live=True,
        entity_type=None,
        jurisdictions=["massachusetts"],
        files=[("client.zip", buf.getvalue())],
    )
    assert out.layers.engagement.documents
    assert any("client.zip" in d.name for d in out.layers.engagement.documents)
    assert any(f.rule_id == "ma.dor.meals" for f in out.findings)


def test_persona_case_file_zip_is_read():
    zpath = DEMO / "mei_case_file.zip"
    assert zpath.exists()
    out = run_visit(
        text="",
        live=True,
        entity_type=EntityType.individual,
        income_band=IncomeBand.hnw,
        jurisdictions=["us-federal", "hong-kong"],
        files=[(zpath.name, zpath.read_bytes())],
    )
    names = " ".join(d.name for d in out.layers.engagement.documents)
    assert "mei_resume.pdf" in names
    assert "mei_worksheet.xlsx" in names
    assert out.findings


def test_pack_id_map():
    assert pack_ids_for(["massachusetts", "hong-kong"]) == ["us-state-ma", "hk-ird"]
    assert pack_ids_for(["china-mainland", "europe"]) == ["cn-sta", "europe"]
    assert pack_ids_for(["australia", "singapore", "canada", "united-kingdom"]) == [
        "au-ato", "sg-iras", "ca-cra", "uk-hmrc",
    ]


def test_hnw_and_family_trust_together():
    out = run_visit(
        text="I am a US person.",
        live=True,
        entity_type=EntityType.individual,
        income_band=IncomeBand.hnw,
        has_family_trust=True,
        jurisdictions=["us-federal"],
    )
    assert out.profile.entity_type.value == "individual"
    assert out.profile.has_family_trust
    assert out.layers.engagement.entity_type == "individual+family_trust"
    assert "family trust" in out.layers.engagement.who.lower()
    assert any(f.rule_id == "us.fed.1041" for f in out.findings)


def test_chen_family_trust_layers():
    out = run_visit(text="", persona_id="chen", jurisdictions=["us-federal"])
    assert "family trust" in out.layers.engagement.who.lower()
    ids = {f.rule_id for f in out.findings}
    assert "us.fed.1041" in ids
    assert "us.fed.founder_public" in ids
    assert "us.fed.fbar" in ids
    assert float(out.profile.foreign_account_total()) == 2_000_000


def test_founder_checkbox_without_persona():
    out = run_visit(
        text="I am a US person.",
        live=True,
        entity_type=None,
        jurisdictions=["us-federal"],
        founder_listed=True,
    )
    assert out.profile.has_founder_listed_stake
    assert any(f.rule_id == "us.fed.founder_public" for f in out.findings)


def test_china_and_europe_open_on_mei():
    out = run_visit(
        text="",
        persona_id="mei",
        jurisdictions=["china-mainland", "europe"],
    )
    ids = {f.rule_id for f in out.findings}
    assert "cn.sta.iit_ties" in ids
    assert "cn.sta.iit_183" not in ids
    assert "eu.vat.oss" in ids
    assert "China mainland" in " ".join(out.layers.engagement.jurisdictions)
    assert "Europe" in " ".join(out.layers.engagement.jurisdictions)
    assert "cn.sta.property" in ids


def test_engagement_seeds_property_alcohol_gst():
    ma = run_visit(
        text="Massachusetts LLC restaurant with employees.",
        live=True,
        entity_type=EntityType.llc,
        jurisdictions=["us-federal", "massachusetts"],
        consider_property=True,
        consider_alcohol=True,
    )
    ids = {f.rule_id for f in ma.findings}
    assert ma.profile.has_property("MA")
    assert ma.profile.has_alcohol()
    assert "ma.dor.property" in ids
    assert "ma.dor.alcohol" in ids
    assert "us.fed.ttb_wine" not in ids

    au = run_visit(
        text="We make taxable supplies in Australia.",
        live=True,
        entity_type=EntityType.llc,
        jurisdictions=["australia"],
        consider_gst=True,
    )
    assert au.profile.has_gst("AU")
    assert any(f.rule_id == "au.ato.gst" for f in au.findings)
    assert not any("Illustrated" in (w.name or "") and w.result not in {"n/a"} for w in au.agency.worksheet)

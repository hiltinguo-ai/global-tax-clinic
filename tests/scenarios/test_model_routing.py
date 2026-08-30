from types import SimpleNamespace

from clinic.models import (
    analyze_wants_bilingual,
    intake_wants_bilingual,
    pick_models,
    route_analyze,
    route_extract,
)


class _FakeClient:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def available(self) -> bool:
        return bool(self._names)

    def list_models(self) -> list[str]:
        return list(self._names)


def test_intake_routes_cjk_and_hk_to_qwen():
    assert intake_wants_bilingual("我是美国税务居民。父母从国内赠与了18万美元。")
    assert intake_wants_bilingual("I keep a Hong Kong bank account at HSBC.")
    assert not intake_wants_bilingual("W-2 hospital worker in Boston. DoorDash on weekends.")


def test_analyze_routes_cn_hk_profile_to_qwen():
    us = SimpleNamespace(residencies=["US"], pack_id="")
    assert not analyze_wants_bilingual(us, [])
    hk = SimpleNamespace(residencies=["US", "HK"])
    assert analyze_wants_bilingual(hk, [])
    finding = SimpleNamespace(pack_id="cn-sta", rule_id="cn.sta.iit_183")
    assert analyze_wants_bilingual(SimpleNamespace(residencies=["US"]), [finding])


def test_pick_models_splits_desks():
    client = _FakeClient(["qwen3.5:4b", "phi4-mini"])
    picked = pick_models(client)
    assert picked["bilingual"] == "qwen3.5:4b"
    assert picked["us_tax"] == "phi4-mini"
    assert picked["extract"] == "qwen3.5:4b"
    assert picked["analyze"] == "phi4-mini"


def test_route_uses_desk_then_falls_back():
    both = _FakeClient(["qwen3.5:4b", "phi4-mini"])
    assert route_extract(both, "父母从国内赠与了18万美元") == "qwen3.5:4b"
    assert route_extract(both, "W-2 in Massachusetts, no foreign accounts") == "phi4-mini"
    qwen_only = _FakeClient(["qwen3.5:4b"])
    assert route_extract(qwen_only, "W-2 in Massachusetts") == "qwen3.5:4b"
    profile = SimpleNamespace(residencies=["US"])
    assert route_analyze(both, profile, []) == "phi4-mini"
    assert route_analyze(both, SimpleNamespace(residencies=["US", "CN"]), []) == "qwen3.5:4b"

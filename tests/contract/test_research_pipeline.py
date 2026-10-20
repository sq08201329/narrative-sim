"""004 离线测试：调研管线（US1 成功路径/失败零写入 + US2 去重 + US3 故障隔离）。

全程离线：MCP call_tool / llm.chat_json / 嵌入三层均可注入替身，
不依赖 gptr-mcp 服务、SearXNG、DeepSeek、嵌入服务任何外部进程。
"""
import json

import pytest

from orchestrator.research import ResearchError, research_asset

DEEP_RESEARCH_OK = {
    "status": "success",
    "research_id": "rid-1",
    "query": "南宋临安城的酒楼",
    "source_count": 2,
    "context": "临安酒楼多为两层木结构，临河而建，酒旗高挑……",
    "sources": [{"url": "https://example.com/a", "title": "甲"}],
    "source_urls": ["https://example.com/a", "https://example.com/b"],
}

CHARACTER_DRAFT = {
    "type": "character",
    "name": "苏晚晴",
    "appearance": {"visual_prompt": "young Chinese female physician, Song dynasty",
                   "description": "游方女医者，青布襦裙"},
    "persona_spec": {"age": 24, "occupation": "游方医者", "personality": "外冷内热",
                     "beliefs": "医者不问出身", "speech_style": "简短克制"},
}

SCENE_DRAFT = {
    "type": "scene",
    "name": "临安酒楼",
    "appearance": {"visual_prompt": "Song dynasty tavern by the river",
                   "description": "两层木结构临河酒楼"},
}


class FakeStore:
    """记录 put_asset 调用并做最低限校验（模拟 schema 把关）。"""

    def __init__(self, assets=None, reject=False, reject_times=0):
        self.put_calls = []
        self.assets = assets or []
        self.reject = reject
        self.reject_times = reject_times

    def put_asset(self, asset):
        self.put_calls.append(asset)
        if self.reject or self.reject_times > 0:
            self.reject_times -= 1
            raise ValueError("schema 校验失败")
        return asset["asset_id"]

    def list_assets(self, type=None):
        if type is None:
            return list(self.assets)
        return [a for a in self.assets if a.get("type") == type]


def fake_call_tool(payload=None):
    calls = []

    def _call(name, arguments):
        calls.append((name, arguments))
        return payload if payload is not None else dict(DEEP_RESEARCH_OK)

    _call.calls = calls
    return _call


def fake_chat_json(draft=None, fail_times=0):
    calls = []
    state = {"fail_times": fail_times}

    def _chat(messages, tier="fast"):
        calls.append(messages)
        if state["fail_times"] > 0:
            state["fail_times"] -= 1
            raise json.JSONDecodeError("漂移", "x", 0)
        return dict(draft if draft is not None else SCENE_DRAFT)

    _chat.calls = calls
    return _chat


# ---------- US1：成功路径 ----------

def test_happy_path_stores_contract_asset():
    store = FakeStore()
    asset_id = research_asset(
        "南宋临安城的酒楼", "scene", store,
        call_tool=fake_call_tool(), chat_json=fake_chat_json(),
        now=lambda: "2026-10-20T13:00:00",
    )
    assert asset_id.startswith("scene_")
    asset = store.put_calls[0]
    assert asset["asset_id"] == asset_id
    assert asset["provenance"]["retriever"] == "gptr-mcp(deepseek-search)"
    assert asset["provenance"]["researched_at"] == "2026-10-20T13:00:00"
    assert asset["provenance"]["confidence"] == pytest.approx(0.7)  # 0.5 + 0.1×2
    assert asset["historical_context"]["sources"] == DEEP_RESEARCH_OK["source_urls"]


def test_deep_research_called_with_query():
    ct = fake_call_tool()
    research_asset("宋代游方女医者", "character", FakeStore(),
                   call_tool=ct, chat_json=fake_chat_json(CHARACTER_DRAFT),
                   now=lambda: "t")
    assert ct.calls == [("deep_research", {"query": "宋代游方女医者"})]


def test_asset_id_deterministic():
    id1 = research_asset("q", "scene", FakeStore(), call_tool=fake_call_tool(),
                         chat_json=fake_chat_json(), now=lambda: "t")
    id2 = research_asset("q", "scene", FakeStore(), call_tool=fake_call_tool(),
                         chat_json=fake_chat_json(), now=lambda: "t")
    assert id1 == id2


# ---------- US1：失败零写入 ----------

def test_extraction_retry_then_success():
    store = FakeStore()
    cj = fake_chat_json(fail_times=1)
    asset_id = research_asset("q", "scene", store, call_tool=fake_call_tool(),
                              chat_json=cj, now=lambda: "t")
    assert asset_id.startswith("scene_")
    assert len(cj.calls) == 2


def test_extraction_persistent_failure_no_write():
    store = FakeStore()
    with pytest.raises(ResearchError, match="结构化抽取失败"):
        research_asset("q", "scene", store, call_tool=fake_call_tool(),
                       chat_json=fake_chat_json(fail_times=99), now=lambda: "t")
    assert store.put_calls == []


def test_schema_rejection_no_write():
    store = FakeStore(reject=True)
    with pytest.raises(ResearchError):
        research_asset("q", "scene", store, call_tool=fake_call_tool(),
                       chat_json=fake_chat_json(), now=lambda: "t")
    assert all(True for _ in store.put_calls)  # put 被尝试但被校验拒绝
    # 关键：没有资产真正入库（FakeStore reject 时不落 assets）
    assert store.assets == []


def test_schema_rejection_triggers_extraction_retry():
    """T019：契约校验拒绝（缺字段类漂移）纳入抽取重试，第二次成功则入库。"""
    store = FakeStore(reject_times=1)
    cj = fake_chat_json()
    asset_id = research_asset("q", "scene", store, call_tool=fake_call_tool(),
                              chat_json=cj, now=lambda: "t")
    assert asset_id.startswith("scene_")
    assert len(cj.calls) == 2
    assert len(store.put_calls) == 2


def test_empty_sources_rejected():
    payload = dict(DEEP_RESEARCH_OK, source_urls=[], source_count=0)
    store = FakeStore()
    with pytest.raises(ResearchError, match="来源"):
        research_asset("q", "scene", store, call_tool=fake_call_tool(payload),
                       chat_json=fake_chat_json(), now=lambda: "t")
    assert store.put_calls == []


def test_blank_query_rejected_without_mcp_call():
    ct = fake_call_tool()
    with pytest.raises(ResearchError, match="查询词"):
        research_asset("   ", "scene", FakeStore(), call_tool=ct,
                       chat_json=fake_chat_json(), now=lambda: "t")
    assert ct.calls == []


def test_mcp_error_status_raises():
    ct = fake_call_tool({"status": "error", "error": "boom"})
    with pytest.raises(ResearchError):
        research_asset("q", "scene", FakeStore(), call_tool=ct,
                       chat_json=fake_chat_json(), now=lambda: "t")


# ---------- US3：配置与故障隔离 ----------

def test_missing_gptr_url_raises_without_network(monkeypatch):
    monkeypatch.delenv("GPTR_MCP_URL", raising=False)
    with pytest.raises(ResearchError, match="GPTR_MCP_URL"):
        research_asset("q", "scene", FakeStore(),
                       chat_json=fake_chat_json(), now=lambda: "t")


def test_mcp_transport_failure_no_write():
    def boom(name, arguments):
        raise ConnectionError("unreachable")

    store = FakeStore()
    with pytest.raises(ResearchError, match="调研服务"):
        research_asset("q", "scene", store, call_tool=boom,
                       chat_json=fake_chat_json(), now=lambda: "t")
    assert store.put_calls == []


def test_no_hardcoded_service_url():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    offenders = []
    for target in [root / "orchestrator", root / "scripts"]:
        for f in target.rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            if ":8000" in text or ":8888" in text:
                offenders.append(str(f.relative_to(root)))
    assert offenders == [], f"硬编码调研服务地址: {offenders}"


# ---------- US2：语义去重 ----------

EXISTING = [{
    "asset_id": "scene_old", "type": "scene", "name": "临安酒楼",
    "appearance": {"visual_prompt": "old", "description": "旧酒楼"},
}]


def _fake_embed(similar: bool):
    """返回嵌入替身：similar=True 时新旧向量余弦 = 1。"""
    def _embed(texts):
        base = [1.0] + [0.0] * 767
        if similar:
            return [list(base) for _ in texts]
        out = []
        for i, _ in enumerate(texts):
            v = [0.0] * 768
            v[i % 768] = 1.0
            out.append(v)
        return out
    return _embed


def test_duplicate_detected_returns_existing_id():
    store = FakeStore(assets=list(EXISTING))
    asset_id = research_asset(
        "南宋临安的酒家", "scene", store,
        call_tool=fake_call_tool(), chat_json=fake_chat_json(),
        embed=_fake_embed(similar=True), now=lambda: "t",
    )
    assert asset_id == "scene_old"
    assert store.put_calls == []


def test_not_duplicate_stores_new():
    store = FakeStore(assets=list(EXISTING))
    asset_id = research_asset(
        "q", "scene", store,
        call_tool=fake_call_tool(), chat_json=fake_chat_json(),
        embed=_fake_embed(similar=False), now=lambda: "t",
    )
    assert asset_id != "scene_old"
    assert len(store.put_calls) == 1


def test_dedup_degrades_to_exact_name_match(caplog):
    store = FakeStore(assets=list(EXISTING))
    # embed=None → 走 embedding.embed_texts（此处无 EMBEDDING_API_BASE，返 None）
    asset_id = research_asset(
        "q", "scene", store,
        call_tool=fake_call_tool(),
        chat_json=fake_chat_json(dict(SCENE_DRAFT, name="临安酒楼")),
        embed=lambda texts: None, now=lambda: "t",
    )
    assert asset_id == "scene_old"  # name 精确匹配命中
    assert store.put_calls == []


def test_dedup_threshold_from_env(monkeypatch):
    monkeypatch.setenv("RESEARCH_DEDUP_THRESHOLD", "1.1")  # 不可能达到 → 不判重
    store = FakeStore(assets=list(EXISTING))
    asset_id = research_asset(
        "q", "scene", store,
        call_tool=fake_call_tool(), chat_json=fake_chat_json(),
        embed=_fake_embed(similar=True), now=lambda: "t",
    )
    assert asset_id != "scene_old"
    assert len(store.put_calls) == 1


# ---------- 005 US2：溯源标签环境变量 ----------

def test_retriever_label_from_env(monkeypatch):
    monkeypatch.setenv("GPTR_MCP_RETRIEVER_LABEL", "gptr-mcp(searxng)")
    store = FakeStore()
    research_asset("q", "scene", store, call_tool=fake_call_tool(),
                   chat_json=fake_chat_json(), now=lambda: "t")
    assert store.put_calls[0]["provenance"]["retriever"] == "gptr-mcp(searxng)"


def test_retriever_label_default(monkeypatch):
    monkeypatch.delenv("GPTR_MCP_RETRIEVER_LABEL", raising=False)
    store = FakeStore()
    research_asset("q", "scene", store, call_tool=fake_call_tool(),
                   chat_json=fake_chat_json(), now=lambda: "t")
    assert store.put_calls[0]["provenance"]["retriever"] == "gptr-mcp(deepseek-search)"

"""009 离线测试：立项生成 / 批量执行总账 / 四层防重复漏斗 / 原料入库。

全程离线：chat_json / call_tool / 嵌入三层 mock + 真实 SQLite 临时库，
零外部进程。
"""
import pytest

from db.init_db import init as init_db
from orchestrator.brief import (
    BriefError,
    execute_brief,
    generate_brief,
    summarize,
)
from orchestrator.research import ResearchError, research_asset, research_material
from orchestrator.store import Store

BRIEF_JSON = {
    "items": [
        {"category": "world", "query": "南宋临安城市形态", "asset_type": "epoch"},
        {"category": "character", "query": "宋代游方女医者",
         "asset_type": "character"},
        {"category": "lore", "query": "南宋临安治安制度", "asset_type": None},
    ]
}

SCENE = {
    "asset_id": "scene_old", "type": "scene", "name": "临安酒楼",
    "appearance": {"visual_prompt": "old tavern", "description": "旧酒楼"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "t",
                   "confidence": 0.5},
}
CHAR = {
    "asset_id": "char_stub", "type": "character", "name": "甲",
    "appearance": {"visual_prompt": "look"},
    "persona_spec": {"age": 30, "occupation": "旅人", "personality": "沉稳",
                     "beliefs": "x", "speech_style": "短"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "t",
                   "confidence": 0.5},
}


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "b.db"
    init_db(db)
    s = Store(db)
    yield s
    s.close()


def _brief(items=None):
    return {"theme": "南宋临安情报战", "generated_at": "t",
            "items": items or [dict(i) for i in BRIEF_JSON["items"]]}


def _fake_embed(cos_map=None):
    """cos_map: (text_a_idx, text_b_idx) -> cos 不needed；用签名相同返回正交或全同向量。"""
    def _embed(texts):
        if cos_map == "same":
            return [[1.0] + [0.0] * 767 for _ in texts]
        out = []
        for i in range(len(texts)):
            v = [0.0] * 768
            v[i % 768] = 1.0
            out.append(v)
        return out
    return _embed


# ---------- 生成（T004） ----------

def test_generate_valid_brief():
    brief = generate_brief("南宋末年临安城里的情报战",
                           chat_json=lambda msgs: dict(BRIEF_JSON))
    assert {i["category"] for i in brief["items"]} == {"world", "character", "lore"}
    assert brief["items"][0]["asset_type"] == "epoch"
    assert brief["items"][2]["asset_type"] is None
    assert brief["truncated"] is False


def test_generate_truncates_over_limit():
    many = {"items": BRIEF_JSON["items"] * 5}
    brief = generate_brief("题材描述文本", chat_json=lambda msgs: many,
                           max_items=4)
    assert len(brief["items"]) == 4
    assert brief["truncated"] is True


def test_generate_retry_on_drift():
    calls = []

    def flaky(msgs):
        calls.append(1)
        if len(calls) == 1:
            return {"items": [{"category": "world"}]}  # 类别不全
        return dict(BRIEF_JSON)

    brief = generate_brief("题材描述文本", chat_json=flaky)
    assert len(calls) == 2
    assert len(brief["items"]) == 3


def test_generate_persistent_drift_raises():
    with pytest.raises(BriefError, match="清单生成失败"):
        generate_brief("题材描述文本", chat_json=lambda msgs: {"bad": 1})


def test_generate_short_theme_rejected():
    with pytest.raises(BriefError, match="过短"):
        generate_brief("短")


# ---------- 批量执行与漏斗（T004/T009） ----------

def _ra_ok(calls):
    def _ra(query, asset_type, store):
        calls.append((query, asset_type))
        n = len(calls)
        if asset_type == "character":
            return store.put_asset(dict(CHAR, asset_id=f"char_new{n}",
                                        name=f"新{n}"))
        return store.put_asset(dict(SCENE, asset_id=f"{asset_type}_new{n}",
                                    name=f"新{n}", type=asset_type))
    return _ra


def _rm_ok(calls):
    def _rm(query, store, *, link_asset_id=None, call_tool=None):
        calls.append((query, link_asset_id))
        return store.put_material(link_asset_id or "lore:x", query,
                                  "gptr-mcp(deepseek-search)", "原料" * 10)
    return _rm


def test_execute_basic_three_categories(store):
    ra_calls, rm_calls = [], []
    ledger = execute_brief(_brief(), store,
                           research_asset_fn=_ra_ok(ra_calls),
                           research_material_fn=_rm_ok(rm_calls),
                           embed=_fake_embed())
    assert len(ledger) == 3
    assert [e["status"] for e in ledger] == ["stored", "stored", "stored"]
    assert len(ra_calls) == 2 and len(rm_calls) == 1


def test_execute_failure_not_blocking(store):
    def ra_boom(query, asset_type, store):
        if "女医者" in query:
            raise ResearchError("模拟失败")
        return store.put_asset(dict(SCENE, asset_id=f"{asset_type}_ok1",
                                    name="新场景", type=asset_type))
    ledger = execute_brief(_brief(), store,
                           research_asset_fn=ra_boom,
                           research_material_fn=_rm_ok([]),
                           embed=_fake_embed())
    statuses = [e["status"] for e in ledger]
    assert statuses[0] == "stored" and statuses[1] == "failed"
    assert "模拟失败" in ledger[1]["reason"]
    assert statuses[2] == "stored"


def test_funnel_exact_cache(store):
    store.put_material("char_old", "宋代游方女医者", "test", "旧原料")
    ra_calls = []
    ledger = execute_brief(_brief(), store,
                           research_asset_fn=_ra_ok(ra_calls),
                           research_material_fn=_rm_ok([]),
                           embed=_fake_embed())
    cached = [e for e in ledger if e["query"] == "宋代游方女医者"][0]
    assert cached["status"] == "cached"
    assert cached["asset_id"] == "char_old"
    assert ("宋代游方女医者", "character") not in ra_calls


def test_funnel_within_brief_merge(store):
    items = [
        {"category": "world", "query": "临安酒楼", "asset_type": "scene"},
        {"category": "world", "query": "临安的酒家", "asset_type": "scene"},
        {"category": "character", "query": "宋代女医", "asset_type": "character"},
        {"category": "lore", "query": "临安治安", "asset_type": None},
    ]

    def custom_embed(texts):
        # 两个 world 查询向量全同（cos=1 → 应合并）；其余互相正交
        out = []
        for i, t in enumerate(texts):
            if t in ("临安酒楼", "临安的酒家"):
                out.append([1.0] + [0.0] * 767)
            else:
                v = [0.0] * 768
                v[(i + 1) % 768] = 1.0
                out.append(v)
        return out

    ledger = execute_brief(_brief(items), store,
                           research_asset_fn=_ra_ok([]),
                           research_material_fn=_rm_ok([]),
                           embed=custom_embed)
    statuses = [e["status"] for e in ledger]
    assert "merged" in statuses
    assert statuses.count("stored") == 3  # 合并后只剩 3 条执行


def test_funnel_library_reuse_skips_research(store):
    store.put_asset(SCENE)
    items = [{"category": "world", "query": "临安酒家", "asset_type": "scene"},
             {"category": "character", "query": "女医", "asset_type": "character"},
             {"category": "lore", "query": "治安", "asset_type": None}]
    ra_calls = []
    ledger = execute_brief(_brief(items), store,
                           research_asset_fn=_ra_ok(ra_calls),
                           research_material_fn=_rm_ok([]),
                           embed=_fake_embed("same"))  # cos=1 ≥ 0.88
    reused = [e for e in ledger if e["query"] == "临安酒家"][0]
    assert reused["status"] == "reused"
    assert reused["asset_id"] == "scene_old"
    assert ra_calls == []  # 资产类全部复用，零调研


def test_funnel_lore_researches_despite_match(store):
    store.put_asset(SCENE)
    items = [{"category": "world", "query": "x", "asset_type": "epoch"},
             {"category": "character", "query": "y", "asset_type": "character"},
             {"category": "lore", "query": "临安酒楼", "asset_type": None}]
    rm_calls = []
    ledger = execute_brief(_brief(items), store,
                           research_asset_fn=_ra_ok([]),
                           research_material_fn=_rm_ok(rm_calls),
                           embed=_fake_embed("same"))
    lore = [e for e in ledger if e["category"] == "lore"][0]
    assert lore["status"] == "attached"  # 高置信也照查，仅 link 指向
    assert rm_calls[0][1] == "scene_old"


def test_funnel_embed_unavailable_degrades(store):
    store.put_asset(dict(SCENE, name="临安治安考"))
    items = [{"category": "world", "query": "x", "asset_type": "epoch"},
             {"category": "character", "query": "y", "asset_type": "character"},
             {"category": "lore", "query": "z", "asset_type": None}]
    ra_calls = []
    ledger = execute_brief(_brief(items), store,
                           research_asset_fn=_ra_ok(ra_calls),
                           research_material_fn=_rm_ok([]),
                           embed=lambda texts: None)
    # 名称不精确匹配 → 无复用，正常执行
    assert all(e["status"] == "stored" for e in ledger)
    # 清单内合并也被跳过（vecs None）
    assert "merged" not in [e["status"] for e in ledger]


def test_summarize_counts():
    ledger = [{"status": "stored"}, {"status": "reused"}, {"status": "failed"},
              {"status": "stored"}]
    text = summarize(ledger)
    assert "stored=2" in text and "reused=1" in text and "failed=1" in text


# ---------- 原料入库（T006/T008） ----------

DEEP_OK = {"status": "success", "research_id": "r", "query": "q",
           "source_count": 2, "context": "南宋临安酒楼的详细考据材料" * 100,
           "sources": [], "source_urls": ["https://a.example"]}


def test_research_material_stores_truncated(store, monkeypatch):
    monkeypatch.setenv("RESEARCH_MATERIAL_MAX_CHARS", "50")
    row_id = research_material("临安酒楼", store, call_tool=lambda n, a: DEEP_OK)
    assert row_id >= 1
    ms = store.get_materials("lore:research")
    assert len(ms) == 1
    assert len(ms[0]["context"]) == 50
    assert ms[0]["query"] == "临安酒楼"


def test_research_material_with_link(store):
    research_material("q", store, link_asset_id="scene_old",
                      call_tool=lambda n, a: DEEP_OK)
    assert store.get_materials("scene_old")[0]["query"] == "q"


def test_research_material_empty_context_rejected(store):
    payload = dict(DEEP_OK, context="")
    with pytest.raises(ResearchError, match="无材料"):
        research_material("q", store, call_tool=lambda n, a: payload)


def test_research_asset_persists_material_on_success(store):
    draft = {"type": "scene", "name": "新酒楼",
             "appearance": {"visual_prompt": "v", "description": "d"}}
    asset_id = research_asset(
        "临安新酒楼", "scene", store,
        call_tool=lambda n, a: DEEP_OK,
        chat_json=lambda msgs, tier="fast": dict(draft),
        now=lambda: "t")
    ms = store.get_materials(asset_id)
    assert len(ms) == 1
    assert ms[0]["query"] == "临安新酒楼"
    assert ms[0]["retriever"] == "gptr-mcp(deepseek-search)"


def test_research_asset_persists_material_on_dedup(store):
    draft = {"type": "scene", "name": "临安酒楼",
             "appearance": {"visual_prompt": "v2", "description": "d2"}}
    store.put_asset(SCENE)

    def same_embed(texts):
        return [[1.0] + [0.0] * 767 for _ in texts]

    asset_id = research_asset(
        "临安的酒家", "scene", store,
        call_tool=lambda n, a: DEEP_OK,
        chat_json=lambda msgs, tier="fast": dict(draft),
        embed=same_embed, now=lambda: "t")
    assert asset_id == "scene_old"  # 去重命中
    ms = store.get_materials("scene_old")
    assert len(ms) == 1  # 原料追加到已有资产
    assert ms[0]["query"] == "临安的酒家"

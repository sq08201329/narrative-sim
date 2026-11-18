"""故事时间树（023）：从纯文本故事抽取时间线索引 + 客观自查。

只整理用户原文已有的事实，不生成新情节。四个自查项均为机器可核对：
schema 结构、source_span 逐字回指、顺序一致、实体去重。全部通过才置 ready。
LLM 调用经可注入的 chat_json_fn 接缝，测试可离线注入假实现（宪章 IV）。
"""
import hashlib
import json
import os
from datetime import datetime, timezone

from .store import SCHEMA_DIR, _validate, SchemaValidationError

CHECK_NAMES = ("schema", "source_span", "order", "dedup")
_PREFIX = {"character": "char", "scene": "scene", "prop": "prop"}
_DEFAULT_MAX_CHARS = 20000
_EVENT_TYPES = ("dialogue", "action", "scene_change", "narration", "inner_voice")


class TreeError(RuntimeError):
    """抽取、自查或锚定失败。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _max_chars() -> int:
    return int(os.environ.get("STORY_TREE_MAX_CHARS", str(_DEFAULT_MAX_CHARS)))


def _key(name: str, etype: str) -> str:
    """规范名 → 确定性 asset_id 形态的实体 key（FR-007 去重依据）。"""
    prefix = _PREFIX.get(etype, etype)
    return f"{prefix}_{hashlib.sha1(name.strip().encode('utf-8')).hexdigest()[:8]}"


def _build_prompt(text: str, limit: int) -> list[dict]:
    return [
        {"role": "system", "content":
         "你是叙事资料整理员，不是编剧。把用户给的纯文本故事按叙述顺序拆成时间节点，"
         "只抽取原文已有事实，不要编造时间、对白或情节。输出严格 JSON 对象，无额外文字。"
         "格式：{\"nodes\":[{\"ord\":1,\"text_time\":\"原文时间词或null\","
         "\"location_name\":\"原文地点名或null\",\"character_names\":[\"原文人名\"],"
         "\"prop_names\":[\"原文道具名\"],"
         "\"event\":{\"type\":\"dialogue|action|scene_change|narration|inner_voice\","
         "\"summary\":\"原文事实摘要\"},\"quote\":\"该节点对应的原文原句（必须逐字）\"}]}。"
         f"最多 {limit} 个节点，ord 从 1 连续递增，quote 必须是输入文本中的连续原句。"},
        {"role": "user", "content": text},
    ]


def _normalize(raw: dict, text: str, tree_id: str) -> dict:
    """把 LLM 输出规范成完整树骨架；source_span 由 quote 在原文中定位得到。"""
    src_nodes = raw.get("nodes")
    if not isinstance(src_nodes, list) or not src_nodes:
        raise TreeError("抽取结果没有节点")

    entities: dict[str, dict] = {}
    nodes: list[dict] = []
    prev_id = None
    for i, item in enumerate(src_nodes, start=1):
        if not isinstance(item, dict):
            raise TreeError(f"第 {i} 个节点格式非法")
        quote = str(item.get("quote") or "")
        pos = text.find(quote) if quote else -1
        # 定位失败也构造出可通过 schema 的 span，交由 source_span 自查明确报出。
        start = pos if pos >= 0 else 0
        end = pos + len(quote) if pos >= 0 else max(1, len(quote))

        text_time = item.get("text_time")
        text_time = str(text_time).strip() if text_time else None
        if text_time and text_time not in text:
            text_time = None  # 原文里不存在的时间词一律不采，避免编造

        loc = str(item.get("location_name") or "").strip() or None
        chars = [str(x).strip() for x in (item.get("character_names") or []) if str(x).strip()]
        props = [str(x).strip() for x in (item.get("prop_names") or []) if str(x).strip()]
        for name, etype in [(loc, "scene")] + [(n, "character") for n in chars] + [
                (n, "prop") for n in props]:
            if name:
                key = _key(name, etype)
                entities.setdefault(key, {"key": key, "type": etype, "name": name})

        event = item.get("event") or {}
        etype = str(event.get("type") or "action")
        if etype not in _EVENT_TYPES:
            etype = "action"
        summary = str(event.get("summary") or "").strip()
        if not summary:
            raise TreeError(f"第 {i} 个节点缺少事件摘要")

        node_id = f"n{i:04d}"
        nodes.append({
            "node_id": node_id,
            "ord": i,
            "parent_node_id": prev_id,
            "text_time": text_time,
            "location_key": _key(loc, "scene") if loc else None,
            "character_keys": [_key(n, "character") for n in chars],
            "prop_keys": [_key(n, "prop") for n in props],
            "event": {"type": etype, "summary": summary},
            "source_span": {"start": start, "end": end, "quote": quote},
        })
        prev_id = node_id

    checked = _now()
    return {
        "tree_id": tree_id,
        "status": "ready",
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "created_at": checked,
        "checked_at": checked,
        "entities": [entities[k] for k in sorted(entities)],
        "nodes": nodes,
        "self_check": {
            "passed": False,
            "checks": [{"name": n, "passed": False, "detail": "未执行"} for n in CHECK_NAMES],
            "failures": [],
            "checked_at": checked,
        },
    }


def _check_schema(tree: dict) -> tuple[bool, str]:
    try:
        schema = json.loads((SCHEMA_DIR / "story_tree.schema.json").read_text(encoding="utf-8"))
        import jsonschema
        jsonschema.validate(tree, schema)
        return True, "契约校验通过"
    except SchemaValidationError as e:
        return False, str(e)
    except Exception as e:  # jsonschema.ValidationError 等
        return False, f"story_tree.schema.json 校验失败: {e.message if hasattr(e, 'message') else e}"


def _check_spans(tree: dict, text: str) -> tuple[bool, str, list[str]]:
    failures = []
    for node in tree["nodes"]:
        span = node["source_span"]
        start, end, quote = span["start"], span["end"], span["quote"]
        if start < 0 or end <= start or end > len(text):
            failures.append(f"{node['node_id']}: source_span 越界")
        elif text[start:end] != quote:
            failures.append(f"{node['node_id']}: source_span 与原文不符")
    return (not failures), (f"{len(tree['nodes'])} 个节点逐字回指通过" if not failures
                            else "; ".join(failures)), failures


def _check_order(tree: dict) -> tuple[bool, str, list[str]]:
    failures = []
    nodes = tree["nodes"]
    for i, node in enumerate(nodes, start=1):
        if node["ord"] != i:
            failures.append(f"{node['node_id']}: ord 应为 {i}，实为 {node['ord']}")
        if node["node_id"] != f"n{i:04d}":
            failures.append(f"{node['node_id']}: node_id 顺序不符")
        expected_parent = None if i == 1 else nodes[i - 2]["node_id"]
        if node["parent_node_id"] != expected_parent:
            failures.append(f"{node['node_id']}: parent_node_id 不符")
    return (not failures), ("顺序连续" if not failures else "; ".join(failures)), failures


def _check_dedup(tree: dict) -> tuple[bool, str, list[str]]:
    failures = []
    keys = [e["key"] for e in tree["entities"]]
    names = [e["name"].strip() for e in tree["entities"]]
    if len(keys) != len(set(keys)):
        failures.append("实体 key 重复")
    if len(names) != len(set(names)):
        failures.append("实体规范名重复")
    known = set(keys)
    for node in tree["nodes"]:
        for ref in [node["location_key"]] + node["character_keys"] + node["prop_keys"]:
            if ref is not None and ref not in known:
                failures.append(f"{node['node_id']}: 引用未定义实体 {ref}")
    return (not failures), ("实体去重通过" if not failures else "; ".join(failures)), failures


def self_check(tree: dict, text: str) -> dict:
    """执行四项客观自查，原地更新 self_check 并返回。"""
    ok_schema, detail_schema = _check_schema(tree)
    ok_span, detail_span, fail_span = _check_spans(tree, text)
    ok_order, detail_order, fail_order = _check_order(tree)
    ok_dedup, detail_dedup, fail_dedup = _check_dedup(tree)
    details = {
        "schema": detail_schema,
        "source_span": detail_span,
        "order": detail_order,
        "dedup": detail_dedup,
    }
    tree["self_check"] = {
        "passed": all([ok_schema, ok_span, ok_order, ok_dedup]),
        "checks": [
            {"name": n, "passed": p, "detail": details[n]}
            for n, p in zip(CHECK_NAMES, [ok_schema, ok_span, ok_order, ok_dedup])
        ],
        "failures": fail_span + fail_order + fail_dedup
                    + ([detail_schema] if not ok_schema else []),
        "checked_at": _now(),
    }
    tree["checked_at"] = tree["self_check"]["checked_at"]
    return tree


def parse_story(text: str, tree_id: str, *, chat_json_fn=None) -> dict:
    """抽取 + 自查；自查失败重试一次，仍失败抛 TreeError（不写库）。"""
    if not isinstance(text, str) or not text.strip():
        raise TreeError("故事文本为空")
    limit = _max_chars()
    if len(text) > limit:
        raise TreeError(f"故事超过 {limit} 字上限（STORY_TREE_MAX_CHARS 可调整）")
    chat = chat_json_fn
    if chat is None:
        from . import llm as _llm
        chat = _llm.chat_json
    last = None
    for _ in range(2):
        try:
            raw = chat(_build_prompt(text, limit))
            tree = _normalize(raw, text, tree_id)
            self_check(tree, text)
            if tree["self_check"]["passed"]:
                return tree
            last = TreeError("自查失败: " + "; ".join(tree["self_check"]["failures"]))
        except TreeError as e:
            last = e
        except Exception as e:
            last = TreeError(f"抽取失败: {type(e).__name__}: {e}")
    raise last or TreeError("抽取失败")


def map_nodes_to_ticks(nodes: list[dict], ticks: int) -> dict[int, str]:
    """把节点按 tick 均分：tick 0 归首节点，其余按序映射。ticks 不足抛错。"""
    if ticks < len(nodes):
        raise TreeError(f"ticks({ticks}) 不得小于节点数({len(nodes)})")
    n = len(nodes)
    mapping = {0: nodes[0]["node_id"]}
    for t in range(1, ticks + 1):
        idx = min((t - 1) * n // ticks, n - 1)
        mapping[t] = nodes[idx]["node_id"]
    return mapping


def build_research_brief(tree: dict) -> dict:
    """实体去重后映射为 brief items（character→character，scene/prop→world）。"""
    items = []
    for ent in tree["entities"]:
        category = "character" if ent["type"] == "character" else "world"
        items.append({"category": category, "query": ent["name"],
                      "asset_type": ent["type"], "link": None})
    return {"theme": f"story-tree:{tree['tree_id']}", "items": items}


def resolve_entity_assets(tree: dict, ledger: list[dict]) -> dict:
    """用 execute_brief 的 ledger 把实体名映射到真实 asset_id。"""
    by_query = {e["query"]: e.get("asset_id") for e in ledger if e.get("asset_id")}
    out = {}
    for ent in tree["entities"]:
        asset_id = by_query.get(ent["name"])
        if asset_id:
            out[ent["key"]] = asset_id
    return out


def _effective_locations(tree: dict) -> dict[str, str]:
    """按节点顺序计算每个节点的有效 location_key（缺省沿用上一个节点）。"""
    out = {}
    current = None
    for node in tree["nodes"]:
        if node["location_key"]:
            current = node["location_key"]
        out[node["node_id"]] = current
    return out


def build_world_specs(tree: dict, entity_assets: dict,
                      base_world_id: str) -> list[dict]:
    """按空间节点分组；world_id={base}__{node_id}，返回建世界所需参数。"""
    eff = _effective_locations(tree)
    groups: dict[str, dict] = {}
    for node in tree["nodes"]:
        loc = eff[node["node_id"]]
        if not loc:
            raise TreeError(f"{node['node_id']}: 没有可解析的空间实体")
        if loc not in entity_assets:
            raise TreeError(f"{node['node_id']}: 空间实体 {loc} 未解析到资产")
        if loc not in groups:
            groups[loc] = {"world_id": f"{base_world_id}__{node['node_id']}",
                           "node_ids": [], "location_id": entity_assets[loc],
                           "character_ids": []}
        groups[loc]["node_ids"].append(node["node_id"])
        for ckey in node["character_keys"]:
            asset_id = entity_assets.get(ckey)
            if not asset_id:
                raise TreeError(f"{node['node_id']}: 角色实体 {ckey} 未解析到资产")
            if asset_id not in groups[loc]["character_ids"]:
                groups[loc]["character_ids"].append(asset_id)
    if not groups:
        raise TreeError("时间树没有空间节点")
    return [groups[k] for k in groups]

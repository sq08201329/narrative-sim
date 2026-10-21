"""幕间记忆传递（012，宪章 II 胶水层）。

- visible_to_character：三规则过滤（inner_voice 仅本人 / visible_to 列内 /
  其余公开，data-model.md）
- generate_memories：过滤 → 双通道摘要（template 确定性 / llm 预算截断）
  → 幂等落库（同键复用零重复计费，regenerate 升版留痕）
- 跨戏交集：目标角色与来源 run 角色取交集，差集标 skipped（FR-009）
"""
import os

from .store import Store

CHANNELS = ("template", "llm")


class InterludeError(RuntimeError):
    """来源 run 不存在 / 通道非法 / llm 通道失败。"""


def visible_to_character(event: dict, asset_id: str,
                         world_characters: list[str]) -> bool:
    """事件 E 对角色 C 可见性（三规则，R2）。"""
    if event.get("type") == "inner_voice":
        return (event.get("characters") or [None])[0] == asset_id
    vt = event.get("visible_to")
    if vt is not None:
        return asset_id in vt
    return asset_id in world_characters


def _template_summary(events: list[dict]) -> str:
    """确定性条目罗列（角色视角由内容原生语序承担）。"""
    return "\n".join(f"第{e['tick']}回合：{e['content']}" for e in events)


def _llm_summary(events: list[dict], character_name: str,
                 chat=None) -> tuple[str, int, int]:
    """真实模型摘要（chat 接缝注入供离线 mock）。返回 (摘要, in, out)。"""
    max_events = int(os.environ.get("INTERLUDE_MAX_EVENTS", "50"))
    max_chars = int(os.environ.get("INTERLUDE_MAX_CHARS", "4000"))
    budget = events[-max_events:]  # 新近优先
    lines = [f"第{e['tick']}回合：{e['content'][:max_chars]}"
             for e in budget]
    if chat is None:
        from .llm import chat_with_usage

        def chat(prompt: str):
            return chat_with_usage([{"role": "user", "content": prompt}])
    prompt = (
        f"你是{character_name}。以下是你在上一幕亲历或耳闻的事件。\n"
        f"请以第一人称「我」写出你的回忆摘要（150 字内，只写你记得的事，"
        f"不要虚构）：\n" + "\n".join(lines))
    return chat(prompt)


def generate_memories(store: Store, run_id: str, character_ids: list[str],
                      channel: str = "template",
                      regenerate: bool = False, chat=None) -> list[dict]:
    """生成/复用幕间记忆（契约 §1）。"""
    if channel not in CHANNELS:
        raise InterludeError(f"BadChannel: 不支持的记忆通道 {channel}")
    if not store.run_exists(run_id):
        raise InterludeError(f"来源 run 不存在: {run_id}")
    events = store.export_events(run_id)
    run_chars = {c for e in events for c in (e.get("characters") or [])}

    results = []
    for cid in character_ids:
        if events and cid not in run_chars:
            results.append({"asset_id": cid, "skipped": True,
                            "reason": "未参与来源 run（跨戏/新角色）"})
            continue
        existing = store.get_memory(run_id, cid)
        if existing is not None and not regenerate:
            results.append({"asset_id": cid, "revision": existing["revision"],
                            "summary": existing["summary"],
                            "event_refs": existing["event_refs"],
                            "channel": existing["channel"],
                            "reused": True, "tokens_in": 0, "tokens_out": 0})
            continue
        visible = [e for e in events
                   if visible_to_character(e, cid, character_ids)]
        tokens_in = tokens_out = 0
        if channel == "llm" and visible:
            name = store.get_asset(cid)["name"]
            summary, tokens_in, tokens_out = _llm_summary(visible, name,
                                                          chat=chat)
        else:
            summary = _template_summary(visible)
        rev = store.put_memory(run_id, cid, summary,
                               [e["event_id"] for e in visible],
                               channel, tokens_in, tokens_out)
        results.append({"asset_id": cid, "revision": rev, "summary": summary,
                        "event_refs": [e["event_id"] for e in visible],
                        "channel": channel, "reused": False,
                        "tokens_in": tokens_in, "tokens_out": tokens_out})
    return results


def get_memories(store: Store, run_id: str,
                 asset_id: str | None = None) -> list[dict]:
    """读取当前版记忆；asset_id 缺省取该 run 全部。无记录返回 []。"""
    if asset_id is not None:
        m = store.get_memory(run_id, asset_id)
        return [m] if m else []
    return store.list_memories(run_id)

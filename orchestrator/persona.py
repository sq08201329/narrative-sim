"""角色后端接缝：PersonaBackend Protocol + 确定性 Mock（宪章原则 IV）。

真实后端（TinyTroupe，M2）只需实现同一 Protocol 即可被链路注入替换。
Mock 无随机、无外部调用：同一输入重复运行产出一致（spec SC-002）。

008 修复：act() 返回动作**列表**——TinyTroupe 协议强制 THINK 在 TALK 之前，
一次 act() 产出的是序列（THINK→TALK→DONE），只取第一个会系统性丢弃 TALK。
"""
from typing import Protocol


class PersonaBackend(Protocol):
    def act(self, persona_spec: dict, visible_state: dict) -> list[dict]:
        """返回动作列表 [{"kind": "dialogue|action|inner_voice", "content": str,
        "emotion": str}, ...]，保持产出顺序（通常内心在前、开口在后）。"""
        ...


class MockPersonaBackend:
    """确定性假后端：按 tick 从内置剧本取动作，可离线重复运行。"""

    _SCRIPT = [
        ("action", "{name}步入厅中，目光扫过在座的每一张脸。", "警觉"),
        ("inner_voice", "今夜这局棋，怕是冲着我来的。", "疑虑"),
        ("dialogue", "诸位久候，在下林昭，初到贵地。", "克制"),
        ("action", "{name}借着添茶的功夫，将纸条压入了壶底。", "镇定"),
    ]

    def act(self, persona_spec: dict, visible_state: dict) -> list[dict]:
        name = persona_spec.get("name", "角色")
        tick = visible_state.get("tick", 1)
        kind, content, emotion = self._SCRIPT[(tick - 1) % len(self._SCRIPT)]
        return [{"kind": kind, "content": content.format(name=name),
                 "emotion": emotion}]

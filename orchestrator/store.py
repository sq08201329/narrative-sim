"""唯一存储入口：SQLite 读写 + 契约校验（宪章原则 I / III）。

其他模块 MUST 通过 Store 访问数据库，MUST NOT 直连 sqlite3。
入库与导出前强制经 schemas/ 校验，失败即拒。
"""
import json
import sqlite3
from functools import lru_cache
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"


class SchemaValidationError(ValueError):
    """契约校验失败。消息格式：<schema名> 校验失败: <JSON路径>: <原因>"""


@lru_cache(maxsize=None)
def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validate(payload: dict, schema_name: str) -> None:
    try:
        jsonschema.validate(payload, _load_schema(schema_name))
    except jsonschema.ValidationError as e:
        path = e.json_path or "$"
        raise SchemaValidationError(
            f"{schema_name} 校验失败: {path}: {e.message}"
        ) from e


class Store:
    """数据库唯一入口。所有读写经此类，外部不得直接连库。"""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    # ---- 资产 ----

    def put_asset(self, asset: dict) -> str:
        _validate(asset, "asset.schema.json")
        payload_json = json.dumps(asset, ensure_ascii=False)
        row = self._conn.execute(
            "SELECT payload FROM assets WHERE asset_id=?", (asset["asset_id"],)
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO assets(asset_id, type, name, status, payload,"
                " current_revision) VALUES(?,?,?,?,?,0)",
                (
                    asset["asset_id"], asset["type"], asset["name"],
                    asset.get("status", "draft"), payload_json,
                ),
            )
            author = (asset.get("provenance") or {}).get("retriever") or "system"
            self._insert_revision(asset["asset_id"], payload_json, None,
                                  "调研原版", author)
        else:
            if self._revision_count(asset["asset_id"]) == 0:
                # 011 前存量资产：以现内容补建 revision 0
                self._insert_revision(asset["asset_id"], row["payload"], None,
                                      "存量资产建档", "system")
            if row["payload"] != payload_json:
                new_rev = self._insert_revision(
                    asset["asset_id"], payload_json, None, "",
                    "system:put_asset")
                self._conn.execute(
                    "UPDATE assets SET payload=?, current_revision=?,"
                    " updated_at=datetime('now') WHERE asset_id=?",
                    (payload_json, new_rev, asset["asset_id"]),
                )
        self._conn.commit()
        return asset["asset_id"]

    # ---- 资产修订（011）----

    def _revision_count(self, asset_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM asset_revisions WHERE asset_id=?",
            (asset_id,),
        ).fetchone()
        return int(row["c"])

    def _insert_revision(self, asset_id: str, payload: str,
                         patch: str | None, reason: str, author: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(revision) + 1, 0) AS n FROM asset_revisions"
            " WHERE asset_id=?", (asset_id,),
        ).fetchone()
        rev = int(row["n"])
        self._conn.execute(
            "INSERT INTO asset_revisions(asset_id, revision, payload, patch,"
            " reason, author) VALUES(?,?,?,?,?,?)",
            (asset_id, rev, payload, patch, reason, author),
        )
        return rev

    def put_revision(self, asset_id: str, payload: str, patch: str | None,
                     reason: str, author: str) -> int:
        """追加修订版并前移当前指针（payload 为新版完整快照 JSON）。"""
        if self._conn.execute(
            "SELECT 1 FROM assets WHERE asset_id=?", (asset_id,),
        ).fetchone() is None:
            raise KeyError(f"资产不存在: {asset_id}")
        if self._revision_count(asset_id) == 0:
            current = self.get_asset(asset_id)
            self._insert_revision(asset_id, json.dumps(current,
                                                       ensure_ascii=False),
                                  None, "存量资产建档", "system")
        rev = self._insert_revision(asset_id, payload, patch, reason, author)
        self._conn.execute(
            "UPDATE assets SET payload=?, current_revision=?,"
            " updated_at=datetime('now') WHERE asset_id=?",
            (payload, rev, asset_id),
        )
        self._conn.commit()
        return rev

    def get_revision(self, asset_id: str, revision: int) -> dict:
        row = self._conn.execute(
            "SELECT * FROM asset_revisions WHERE asset_id=? AND revision=?",
            (asset_id, revision),
        ).fetchone()
        if row is None:
            raise KeyError(f"修订版不存在: {asset_id}@r{revision}")
        return dict(row)

    def list_revisions(self, asset_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM asset_revisions WHERE asset_id=? ORDER BY revision",
            (asset_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_asset_at_revision(self, asset_id: str, revision: int) -> dict:
        return json.loads(self.get_revision(asset_id, revision)["payload"])

    def set_current_revision(self, asset_id: str, revision: int) -> None:
        """指针回指并回填该版快照（rollback 原语，历史不删）。"""
        snap = self.get_revision(asset_id, revision)["payload"]
        cur = self._conn.execute(
            "UPDATE assets SET payload=?, current_revision=?,"
            " updated_at=datetime('now') WHERE asset_id=?",
            (snap, revision, asset_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"资产不存在: {asset_id}")
        self._conn.commit()

    def current_revision(self, asset_id: str) -> int:
        row = self._conn.execute(
            "SELECT current_revision FROM assets WHERE asset_id=?", (asset_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"资产不存在: {asset_id}")
        return int(row["current_revision"])

    def get_asset(self, asset_id: str) -> dict:
        row = self._conn.execute(
            "SELECT payload FROM assets WHERE asset_id=?", (asset_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"资产不存在: {asset_id}")
        return json.loads(row["payload"])

    def list_assets(self, type: str | None = None) -> list[dict]:
        """按类型列出资产（调研去重用）；type 为 None 时列全部。"""
        if type is None:
            rows = self._conn.execute("SELECT payload FROM assets").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM assets WHERE type=?", (type,)
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ---- 运行与世界 ----

    def run_exists(self, run_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        return row is not None

    def create_run(self, run_id: str, world_id: str) -> None:
        if self.run_exists(run_id):
            raise ValueError(f"run_id 已存在: {run_id}（如需重跑请先 reset_run）")
        self._conn.execute(
            "INSERT OR IGNORE INTO worlds(world_id, config) VALUES(?, '')", (world_id,)
        )
        self._conn.execute(
            "INSERT INTO runs(run_id, world_id) VALUES(?,?)", (run_id, world_id)
        )
        self._conn.commit()

    def reset_run(self, run_id: str) -> None:
        """删除某次运行及其全部事件（显式重跑，不静默覆盖）。"""
        self._conn.execute("DELETE FROM events WHERE run_id=?", (run_id,))
        self._conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
        self._conn.commit()

    def finish_run(self, run_id: str, status: str = "done") -> None:
        self._conn.execute(
            "UPDATE runs SET status=?, ended_at=datetime('now') WHERE run_id=?",
            (status, run_id),
        )
        self._conn.commit()

    # ---- 世界状态快照（006） ----

    def put_world_config(self, world_id: str, config_json: str) -> None:
        """写入世界定义（007 M5：create_world 与 run_simulation 的衔接）。"""
        self._conn.execute(
            "INSERT INTO worlds(world_id, config) VALUES(?, ?)"
            " ON CONFLICT(world_id) DO UPDATE SET config=excluded.config,"
            " updated_at=datetime('now')",
            (world_id, config_json),
        )
        self._conn.commit()

    def get_world_config(self, world_id: str) -> dict | None:
        import json as _json
        row = self._conn.execute(
            "SELECT config FROM worlds WHERE world_id=?", (world_id,)
        ).fetchone()
        if row is None or not row["config"]:
            return None
        return _json.loads(row["config"])

    def put_world_state(self, world_id: str, tick: int, state_json: str) -> None:
        self._conn.execute(
            "UPDATE worlds SET state=?, tick=?, updated_at=datetime('now')"
            " WHERE world_id=?",
            (state_json, tick, world_id),
        )
        self._conn.commit()

    def get_world_state(self, world_id: str) -> tuple[int, str] | None:
        row = self._conn.execute(
            "SELECT tick, state FROM worlds WHERE world_id=?", (world_id,)
        ).fetchone()
        if row is None or row["state"] is None:
            return None
        return int(row["tick"]), row["state"]

    # ---- 调研原料（009） ----

    def put_material(self, asset_id: str, query: str, retriever: str,
                     context: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO research_materials(asset_id, query, retriever, context)"
            " VALUES(?,?,?,?)",
            (asset_id, query, retriever, context),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_materials(self, asset_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, asset_id, query, retriever, context, created_at"
            " FROM research_materials WHERE asset_id=? ORDER BY id",
            (asset_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_material_by_query(self, query: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, asset_id, query, retriever, context, created_at"
            " FROM research_materials WHERE query=? ORDER BY id DESC LIMIT 1",
            (query,),
        ).fetchone()
        return dict(row) if row else None

    def max_event_no(self) -> int:
        """全库事件编号最大值（event_id 全局唯一，编号分配需跨运行连续）。"""
        row = self._conn.execute(
            "SELECT MAX(CAST(SUBSTR(event_id, 2) AS INTEGER)) AS m FROM events"
        ).fetchone()
        return row["m"] or 0

    def update_run_cost(self, run_id: str, total_tokens: int) -> None:
        """按 run_id 聚合写入 token 用量（宪章原则 VI）。"""
        cur = self._conn.execute(
            "UPDATE runs SET token_cost=? WHERE run_id=?", (total_tokens, run_id)
        )
        if cur.rowcount == 0:
            raise KeyError(f"运行不存在: {run_id}")
        self._conn.commit()

    # ---- 事件 ----

    def put_event(self, event: dict) -> None:
        _validate(event, "event.schema.json")
        self._conn.execute(
            "INSERT INTO events(event_id, run_id, tick, seq, type, payload)"
            " VALUES(?,?,?,?,?,?)",
            (
                event["event_id"], event["run_id"], event["tick"],
                event.get("seq", 0), event["type"],
                json.dumps(event, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def export_events(self, run_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT payload FROM events WHERE run_id=? ORDER BY tick, seq", (run_id,)
        ).fetchall()
        events = [json.loads(r["payload"]) for r in rows]
        for ev in events:
            _validate(ev, "event.schema.json")
        return events

    # ---- 裁决审计（010）----

    def put_dm_call(self, run_id: str, tick: int, action: str, agent_id: str,
                    params: str, hint: str, narrative: str, effects: str,
                    tokens_in: int, tokens_out: int, elapsed_s: float,
                    failed: bool) -> int:
        cur = self._conn.execute(
            "INSERT INTO dm_calls(run_id, tick, action, agent_id, params, hint,"
            " narrative, effects, tokens_in, tokens_out, elapsed_s, failed)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, tick, action, agent_id, params, hint, narrative, effects,
             tokens_in, tokens_out, elapsed_s, int(failed)),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_dm_calls(self, run_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM dm_calls WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

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
        self._conn.execute(
            "INSERT OR REPLACE INTO assets(asset_id, type, name, status, payload)"
            " VALUES(?,?,?,?,?)",
            (
                asset["asset_id"], asset["type"], asset["name"],
                asset.get("status", "draft"),
                json.dumps(asset, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return asset["asset_id"]

    def get_asset(self, asset_id: str) -> dict:
        row = self._conn.execute(
            "SELECT payload FROM assets WHERE asset_id=?", (asset_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"资产不存在: {asset_id}")
        return json.loads(row["payload"])

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

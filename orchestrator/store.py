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


def _canon_json(text: str) -> str:
    """按语义规范化 JSON 文本（键排序），用于内容一致性判定。"""
    try:
        return json.dumps(json.loads(text), sort_keys=True, ensure_ascii=False)
    except ValueError:
        return text


_IMAGE_REF_FIELD = "reference_images"


def _strip_image_refs(asset: dict) -> dict:
    """当前 payload 不存 reference_images——该字段由 image_generations 派生。"""
    asset.pop(_IMAGE_REF_FIELD, None)
    return asset


def _strip_image_refs_json(payload_json: str) -> str:
    """JSON 版本的剥离（不动历史修订行，只用于写入当前 payload 前）。"""
    try:
        obj = json.loads(payload_json)
    except ValueError:
        return payload_json
    if isinstance(obj, dict) and _IMAGE_REF_FIELD in obj:
        obj.pop(_IMAGE_REF_FIELD)
        return json.dumps(obj, ensure_ascii=False)
    return payload_json


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
        """追加修订版并前移当前指针（payload 为新版完整快照 JSON）。

        reference_images 不进修订内容（由 image_generations 派生），写入前剥离。
        """
        if self._conn.execute(
            "SELECT 1 FROM assets WHERE asset_id=?", (asset_id,),
        ).fetchone() is None:
            raise KeyError(f"资产不存在: {asset_id}")
        payload = _strip_image_refs_json(payload)
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
        return _strip_image_refs(
            json.loads(self.get_revision(asset_id, revision)["payload"]))

    def set_current_revision(self, asset_id: str, revision: int) -> None:
        """指针回指并回填该版快照（rollback 原语，历史不删）。

        reference_images 不再进当前 payload（由 image_generations 派生），
        回填时剥离，避免历史字段复活。
        """
        snap = _strip_image_refs_json(self.get_revision(asset_id, revision)["payload"])
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

    def ensure_revision0(self, asset_id: str) -> None:
        """存量资产（011 前入库、无修订行）以当前内容补建 revision 0，
        保证版号锚点可解析（幂等）。"""
        if self._revision_count(asset_id) > 0:
            return
        current = self.get_asset(asset_id)
        self._insert_revision(asset_id, json.dumps(current,
                                                   ensure_ascii=False),
                              None, "存量资产建档", "system")
        self._conn.commit()

    # ---- 导入专用（asset_port，保号写入；不改 put_asset / put_revision 语义）----

    _IMPORT_TYPES = ("character", "prop", "scene", "epoch")

    def import_asset_row(self, asset: dict, revisions: list[dict]) -> None:
        """导入专用：按原修订号写入资产行与其修订（单事务，失败整体回滚）。

        asset: {asset_id, type, name, status, payload, current_revision}
        revisions: [{revision, payload, patch, reason, author, created_at}]

        - type 必须在 character/prop/scene/epoch 内；
        - asset.payload 经 asset.schema.json 校验；
        - current_revision 必须被同批修订（或库内已有修订）覆盖，否则报错；
        - 资产行已存在时更新 payload/name/status/current_revision，不新建版本。
        冲突判定与导入计划由调用方（asset_port）负责；本方法只落库。
        """
        aid = asset.get("asset_id")
        if not aid:
            raise ValueError("导入资产缺少 asset_id")
        atype = asset.get("type")
        if atype not in self._IMPORT_TYPES:
            raise ValueError(
                f"非法资产类型: {atype}（只能是 character/prop/scene/epoch）")
        name = asset.get("name")
        if not name:
            raise ValueError("导入资产缺少 name")
        payload = asset.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("导入资产 payload 必须是对象")
        payload = _strip_image_refs(dict(payload))
        _validate(payload, "asset.schema.json")
        cur = asset.get("current_revision")
        if not isinstance(cur, int) or cur < 0:
            raise ValueError(f"current_revision 非法: {cur!r}")
        payload_json = json.dumps(payload, ensure_ascii=False)

        try:
            self._conn.execute("BEGIN")
            exists = self._conn.execute(
                "SELECT 1 FROM assets WHERE asset_id=?", (aid,)).fetchone()
            if exists is None:
                self._conn.execute(
                    "INSERT INTO assets(asset_id, type, name, status, payload,"
                    " current_revision) VALUES(?,?,?,?,?,?)",
                    (aid, atype, name, asset.get("status", "draft"),
                     payload_json, cur),
                )
            else:
                self._conn.execute(
                    "UPDATE assets SET type=?, name=?, status=?, payload=?,"
                    " current_revision=?, updated_at=datetime('now')"
                    " WHERE asset_id=?",
                    (atype, name, asset.get("status", "draft"),
                     payload_json, cur, aid),
                )
            for rev in revisions:
                self.upsert_revision_at(
                    aid, rev["revision"], rev["payload"],
                    patch=rev.get("patch"), reason=rev.get("reason", ""),
                    author=rev.get("author", "system"),
                    created_at=rev.get("created_at"))
            covered = self._conn.execute(
                "SELECT 1 FROM asset_revisions WHERE asset_id=? AND revision=?",
                (aid, cur)).fetchone()
            if covered is None:
                raise ValueError(f"current_revision {cur} 未被修订覆盖: {aid}")
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def upsert_revision_at(self, asset_id: str, revision: int, payload: dict,
                           patch: str | None = None, reason: str = "",
                           author: str = "system",
                           created_at: str | None = None) -> int:
        """导入专用：按指定修订号写入（保号，不重新分配号）。

        同号同内容 → 幂等跳过并返回该号；同号不同内容 → ValueError（冲突）。
        单独调用时自持事务；被 import_asset_row 调用时加入其事务。
        """
        if not isinstance(revision, int) or revision < 0:
            raise ValueError(f"修订号非法: {revision!r}")
        if not isinstance(payload, dict):
            raise ValueError("修订 payload 必须是对象")
        payload = _strip_image_refs(dict(payload))
        if self._conn.execute(
                "SELECT 1 FROM assets WHERE asset_id=?", (asset_id,),
        ).fetchone() is None:
            raise KeyError(f"资产不存在: {asset_id}")
        payload_json = json.dumps(payload, ensure_ascii=False)
        own_tx = not self._conn.in_transaction
        try:
            if own_tx:
                self._conn.execute("BEGIN")
            row = self._conn.execute(
                "SELECT payload FROM asset_revisions"
                " WHERE asset_id=? AND revision=?",
                (asset_id, revision)).fetchone()
            if row is not None:
                if _canon_json(row["payload"]) != _canon_json(payload_json):
                    raise ValueError(
                        f"修订冲突: {asset_id}@r{revision}（同号不同内容）")
                if own_tx:
                    self._conn.commit()
                return revision
            if created_at:
                self._conn.execute(
                    "INSERT INTO asset_revisions(asset_id, revision, payload,"
                    " patch, reason, author, created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (asset_id, revision, payload_json, patch, reason, author,
                     created_at))
            else:
                self._conn.execute(
                    "INSERT INTO asset_revisions(asset_id, revision, payload,"
                    " patch, reason, author) VALUES(?,?,?,?,?,?)",
                    (asset_id, revision, payload_json, patch, reason, author))
            if own_tx:
                self._conn.commit()
            return revision
        except Exception:
            if own_tx:
                self._conn.rollback()
            raise

    def reference_images(self, asset_id: str) -> list[str]:
        """从 image_generations 派生 reference_images（A1 口径）。

        结构沿用既有契约：相对路径字符串数组。排序必须确定：
        按 (出图时间, sha256, 路径) 升序，再按路径去重（保留最早登记）。
        """
        entries = []
        for gen in self.list_image_generations(asset_id):
            paths = gen.get("paths") or []
            hashes = gen.get("sha256") or []
            for i, path in enumerate(paths):
                sha = hashes[i] if i < len(hashes) else ""
                entries.append((gen.get("created_at") or "", sha or "", path))
        entries.sort()
        out: list[str] = []
        seen: set[str] = set()
        for _, _, path in entries:
            if path in seen:
                continue
            seen.add(path)
            out.append(path)
        return out

    def list_world_configs(self) -> list[dict]:
        """全部世界的 {world_id, config(已解析)}（修订 impacted 反查用）。"""
        rows = self._conn.execute(
            "SELECT world_id, config FROM worlds"
        ).fetchall()
        out = []
        for r in rows:
            try:
                cfg = json.loads(r["config"]) if r["config"] else {}
            except ValueError:
                cfg = {}
            out.append({"world_id": r["world_id"], "config": cfg})
        return out

    def list_runs(self, world_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT run_id FROM runs WHERE world_id=? ORDER BY started_at",
            (world_id,),
        ).fetchall()
        return [r["run_id"] for r in rows]

    def get_asset(self, asset_id: str) -> dict:
        row = self._conn.execute(
            "SELECT payload FROM assets WHERE asset_id=?", (asset_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"资产不存在: {asset_id}")
        asset = _strip_image_refs(json.loads(row["payload"]))
        images = self.reference_images(asset_id)
        if images:
            asset[_IMAGE_REF_FIELD] = images
        return asset

    def list_assets(self, type: str | None = None) -> list[dict]:
        """按类型列出资产（调研去重用）；type 为 None 时列全部。"""
        if type is None:
            rows = self._conn.execute("SELECT payload FROM assets").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM assets WHERE type=?", (type,)
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def list_asset_summaries(self, type: str | None = None) -> list[dict]:
        """资产概要（011 MCP list_assets）：含当前修订版号，按 asset_id 排序。"""
        sql = ("SELECT asset_id, type, name, status, current_revision,"
               " created_at FROM assets")
        args: tuple = ()
        if type is not None:
            sql += " WHERE type=?"
            args = (type,)
        rows = self._conn.execute(sql + " ORDER BY asset_id", args).fetchall()
        return [dict(r) for r in rows]

    def search_materials(self, keyword: str) -> list[dict]:
        """原料关键词检索（query/context 子串，大小写不敏感）。"""
        rows = self._conn.execute(
            "SELECT id, asset_id, query, retriever, context, created_at"
            " FROM research_materials"
            " WHERE lower(query) LIKE ? OR lower(context) LIKE ?"
            " ORDER BY id",
            (f"%{keyword.lower()}%", f"%{keyword.lower()}%"),
        ).fetchall()
        return [dict(r) for r in rows]

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

    # ---- 参考图生成记录（013）----

    def put_image_generation(self, asset_id: str, prompt: str, n: int,
                             aspect_ratio: str, paths: list[str],
                             sha256: list[str], provider: str,
                             asset_revision: int) -> int:
        cur = self._conn.execute(
            "INSERT INTO image_generations(asset_id, prompt, n, aspect_ratio,"
            " paths, sha256, provider, asset_revision)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (asset_id, prompt, n, aspect_ratio,
             json.dumps(paths, ensure_ascii=False),
             json.dumps(sha256, ensure_ascii=False), provider,
             asset_revision),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_image_generations(self, asset_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM image_generations WHERE asset_id=? ORDER BY id",
            (asset_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["paths"] = json.loads(d["paths"])
            d["sha256"] = json.loads(d["sha256"])
            out.append(d)
        return out

    # ---- 幕间记忆（012）----
    def put_memory(self, run_id: str, asset_id: str, summary: str,
                   event_refs: list[str], channel: str,
                   tokens_in: int = 0, tokens_out: int = 0,
                   reason: str = "") -> int:
        """同 (run_id, asset_id) 自动升 revision 追加，返回新版号。"""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(revision) + 1, 1) AS n FROM interlude_memories"
            " WHERE run_id=? AND asset_id=?", (run_id, asset_id),
        ).fetchone()
        rev = int(row["n"])
        self._conn.execute(
            "INSERT INTO interlude_memories(run_id, asset_id, revision,"
            " summary, event_refs, channel, reason, tokens_in, tokens_out)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (run_id, asset_id, rev, summary,
             json.dumps(event_refs, ensure_ascii=False), channel,
             reason, tokens_in, tokens_out),
        )
        self._conn.commit()
        return rev

    def get_memory(self, run_id: str, asset_id: str) -> dict | None:
        """当前版（MAX revision）；无记录返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM interlude_memories WHERE run_id=? AND asset_id=?"
            " ORDER BY revision DESC LIMIT 1", (run_id, asset_id),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["event_refs"] = json.loads(d["event_refs"])
        return d

    def list_memories(self, run_id: str) -> list[dict]:
        """该 run 每角色当前版记忆。"""
        rows = self._conn.execute(
            "SELECT m.* FROM interlude_memories m"
            " JOIN (SELECT asset_id, MAX(revision) AS mr"
            "       FROM interlude_memories WHERE run_id=? GROUP BY asset_id) t"
            " ON m.run_id=? AND m.asset_id=t.asset_id AND m.revision=t.mr"
            " ORDER BY m.asset_id", (run_id, run_id),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["event_refs"] = json.loads(d["event_refs"])
            out.append(d)
        return out

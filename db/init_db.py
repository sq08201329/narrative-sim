"""SQLite 初始化：资产库 / 世界状态 / 运行记录 / 事件日志。

幂等：重复执行不报错、不破坏既有数据（宪章原则 III）。
"""
import sqlite3
import sys
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id   TEXT PRIMARY KEY,
    type       TEXT NOT NULL CHECK (type IN ('character','prop','scene','epoch')),
    name       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'draft',
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);

CREATE TABLE IF NOT EXISTS worlds (
    world_id   TEXT PRIMARY KEY,
    config     TEXT NOT NULL DEFAULT '',
    state      TEXT,
    tick       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    world_id   TEXT NOT NULL REFERENCES worlds(world_id),
    status     TEXT NOT NULL DEFAULT 'running',
    token_cost REAL NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at   TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,
    run_id     TEXT NOT NULL REFERENCES runs(run_id),
    tick       INTEGER NOT NULL,
    seq        INTEGER NOT NULL DEFAULT 0,
    type       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, tick, seq);

CREATE TABLE IF NOT EXISTS research_materials (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id   TEXT NOT NULL,
    query      TEXT NOT NULL,
    retriever  TEXT NOT NULL,
    context    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_materials_asset ON research_materials(asset_id);
CREATE INDEX IF NOT EXISTS idx_materials_query ON research_materials(query);

CREATE TABLE IF NOT EXISTS dm_calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL REFERENCES runs(run_id),
    tick       INTEGER NOT NULL,
    action     TEXT NOT NULL,
    agent_id   TEXT NOT NULL,
    params     TEXT NOT NULL,
    hint       TEXT,
    narrative  TEXT,
    effects    TEXT NOT NULL,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    elapsed_s  REAL NOT NULL DEFAULT 0,
    failed     INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dm_calls_run ON dm_calls(run_id);

CREATE TABLE IF NOT EXISTS asset_revisions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id   TEXT NOT NULL REFERENCES assets(asset_id),
    revision   INTEGER NOT NULL,
    payload    TEXT NOT NULL,
    patch      TEXT,
    reason     TEXT NOT NULL DEFAULT '',
    author     TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(asset_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_revisions_asset ON asset_revisions(asset_id);

CREATE TABLE IF NOT EXISTS interlude_memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL REFERENCES runs(run_id),
    asset_id   TEXT NOT NULL REFERENCES assets(asset_id),
    revision   INTEGER NOT NULL DEFAULT 1,
    summary    TEXT NOT NULL,
    event_refs TEXT NOT NULL,
    channel    TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(run_id, asset_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_interlude_run ON interlude_memories(run_id, asset_id);

CREATE TABLE IF NOT EXISTS image_generations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id       TEXT NOT NULL REFERENCES assets(asset_id),
    prompt         TEXT NOT NULL,
    n              INTEGER NOT NULL,
    aspect_ratio   TEXT NOT NULL,
    paths          TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    provider       TEXT NOT NULL,
    asset_revision INTEGER NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_image_gen_asset ON image_generations(asset_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """老库幂等迁移：assets 缺 current_revision 列时补上（011）；
    interlude_memories 缺 reason 列时补上（012 T018）。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)").fetchall()}
    if "current_revision" not in cols:
        conn.execute(
            "ALTER TABLE assets ADD COLUMN current_revision"
            " INTEGER NOT NULL DEFAULT 0"
        )
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(interlude_memories)").fetchall()}
    if cols and "reason" not in cols:
        conn.execute(
            "ALTER TABLE interlude_memories ADD COLUMN reason"
            " TEXT NOT NULL DEFAULT ''"
        )


def init(db_path: str) -> str:
    """建库建表（幂等），返回数据库路径。"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DDL)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
    return db_path


if __name__ == "__main__":
    target = init(sys.argv[1] if len(sys.argv) > 1 else "narrative_sim.db")
    print(f"数据库已初始化: {target}")

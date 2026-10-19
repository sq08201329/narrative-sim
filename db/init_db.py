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
"""


def init(db_path: str) -> str:
    """建库建表（幂等），返回数据库路径。"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DDL)
    finally:
        conn.close()
    return db_path


if __name__ == "__main__":
    target = init(sys.argv[1] if len(sys.argv) > 1 else "narrative_sim.db")
    print(f"数据库已初始化: {target}")

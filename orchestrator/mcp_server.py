"""MCP Server 协议封装（M5，宪章原则 II：只做协议封装，业务全在 orchestrator）。

六个工具 = 类型标注 + docstring（fastmcp 自动出 schema）+ 薄错误兜底：
- 编排异常统一兜为 ToolError("{类型}: {原因}")，客户端拿到结构化可读错误，
  server 进程不崩（FR-004）
- 业务实现全部来自既有模块：research.py / world.py / simulation.py /
  store.py / gptr_deepseek_retriever（SC-004 grep 门禁）
- 启动零外部检查：gptr-mcp/嵌入服务不在线不影响 server 启动，
  工具调用时按各自口径报错或降级（Edge Case）
"""
import json
import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from gptr_deepseek_retriever import web_fetch as _web_fetch
from gptr_deepseek_retriever import web_search as _web_search

from db.init_db import init as _init_db
from .persona import MockPersonaBackend
from .research import research_asset as _research_asset
from .simulation import export_jsonl as _export_jsonl
from .store import Store
from .world import build_scene_config as _build_scene_config
from .world import run_world as _run_world

DEFAULT_DB = "narrative_sim.db"


def _db_path() -> str:
    return os.environ.get("NARRATIVE_DB", DEFAULT_DB)


def _store() -> Store:
    _init_db(_db_path())
    return Store(_db_path())


def _fail(exc: Exception) -> ToolError:
    return ToolError(f"{type(exc).__name__}: {exc}")


def build_server() -> FastMCP:
    mcp = FastMCP("narrative-sim")

    @mcp.tool()
    def research_asset(query: str, asset_type: str) -> dict:
        """调研一个资产（人物/场景/道具/时代）并校验入库。
        返回 {asset_id, deduplicated}；deduplicated=True 表示命中已有资产未新写入。"""
        store = _store()
        try:
            before = len(store.list_assets(asset_type))
            asset_id = _research_asset(query, asset_type, store)
            after = len(store.list_assets(asset_type))
            return {"asset_id": asset_id, "deduplicated": after == before}
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def create_world(world_id: str, character_ids: list[str],
                     location_id: str, reset: bool = False) -> dict:
        """从资产库组装世界并登记（world_id 供 run_simulation 使用）。
        资产缺失会明确指出缺口；world_id 已存在时需 reset=True 覆盖。"""
        store = _store()
        try:
            if store.get_world_config(world_id) is not None and not reset:
                raise ToolError(
                    f"WorldExists: world {world_id} 已存在（reset=True 可覆盖）")
            cfg = _build_scene_config(store, character_ids, location_id)
            store.put_world_config(world_id, json.dumps(
                {"character_ids": character_ids, "location_id": location_id},
                ensure_ascii=False))
            return {"world_id": world_id, "characters": character_ids,
                    "location": location_id, "action_count": len(cfg["actions"])}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def run_simulation(world_id: str, run_id: str, ticks: int,
                       backend: str = "tinytroupe",
                       resume: bool = False) -> dict:
        """跑仿真：world_id 需先 create_world；resume=True 从最近快照续跑。
        backend=tinytroupe（默认真后端，每 tick 每角色约 15-30s）或 mock（离线演示）。
        返回 {run_id, event_count, ticks, cost_tokens}。"""
        store = _store()
        try:
            cfg = store.get_world_config(world_id)
            if cfg is None:
                raise ToolError(
                    f"WorldNotFound: world {world_id} 不存在（先 create_world）")
            if backend == "mock":
                be = MockPersonaBackend()
                tokens = None
            else:
                from .persona_tinytroupe import TinyTroupeBackend
                be = TinyTroupeBackend()
                be.reset_cost_stats()
            events = _run_world(store, run_id, world_id, cfg["character_ids"],
                                cfg["location_id"], ticks, be, resume=resume)
            cost = None
            if backend != "mock":
                cost = be.collect_total_tokens()
                store.update_run_cost(run_id, cost)
            return {"run_id": run_id, "event_count": len(events),
                    "ticks": ticks, "cost_tokens": cost}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def export_events(run_id: str, out_path: str) -> dict:
        """按 tick/seq 导出某次运行的事件流为 JSONL（导出前逐条复验契约）。"""
        store = _store()
        try:
            if not store.run_exists(run_id):
                raise ToolError(f"RunNotFound: run {run_id} 不存在")
            count = len(store.export_events(run_id))
            path = _export_jsonl(store, run_id, out_path)
            return {"path": path, "count": count}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def web_search(query: str, count: int = 8) -> dict:
        """DeepSeek 网页搜索：返回 [{title, url, summary}]，无结果为空列表。"""
        try:
            results = _web_search(query, count=count)
            return {"results": [
                {"title": r.get("title", ""), "url": r.get("url", ""),
                 "summary": r.get("summary") or r.get("snippet", "")}
                for r in results
            ]}
        except Exception as e:
            raise _fail(e) from e

    @mcp.tool()
    def web_fetch(url: str) -> dict:
        """DeepSeek 网页抓取：返回 {title, content}（Markdown 正文）。"""
        page = _web_fetch(url)
        if page is None:
            raise ToolError("FetchFailed: 目标页不可抓取或无可提取正文")
        return page

    return mcp

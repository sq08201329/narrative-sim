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
                     location_id: str, reset: bool = False,
                     memory_from: str | None = None) -> dict:
        """从资产库组装世界并登记（world_id 供 run_simulation 使用）。
        资产缺失会明确指出缺口；world_id 已存在时需 reset=True 覆盖。
        建世界时冻结各资产的修订版号（011 FR-008），后续修订不影响本世界。
        memory_from 指定上一幕来源 run（012），其角色记忆将在起跑时注入。"""
        store = _store()
        try:
            if store.get_world_config(world_id) is not None and not reset:
                raise ToolError(
                    f"WorldExists: world {world_id} 已存在（reset=True 可覆盖）")
            cfg = _build_scene_config(store, character_ids, location_id)
            pins = {aid: store.current_revision(aid)
                    for aid in [*character_ids, location_id]}
            store.put_world_config(world_id, json.dumps(
                {"character_ids": character_ids, "location_id": location_id,
                 "revisions": pins, "memory_from": memory_from},
                ensure_ascii=False))
            return {"world_id": world_id, "characters": character_ids,
                    "location": location_id, "action_count": len(cfg["actions"]),
                    "revision_pins": pins, "memory_from": memory_from}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def run_simulation(world_id: str, run_id: str, ticks: int,
                       backend: str = "tinytroupe",
                       resume: bool = False, dm: bool = False,
                       dm_max_calls: int = 50,
                       dm_knowledge_chars: int = 2000,
                       memory_from: str | None = None) -> dict:
        """跑仿真：world_id 需先 create_world；resume=True 从最近快照续跑。
        backend=tinytroupe（默认真后端，每 tick 每角色约 15-30s）或 mock（离线演示）。
        dm=True 启用真实裁决（010，需 DEEPSEEK_API_KEY，每次裁决一次模型调用）。
        返回 {run_id, event_count, ticks, cost_tokens}；dm=True 时另含
        dm_calls/dm_failed。"""
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
            dm_options = None
            if dm:
                from .world import DMOptions
                dm_options = DMOptions(knowledge_chars=dm_knowledge_chars,
                                       max_calls=dm_max_calls)
            events = _run_world(store, run_id, world_id, cfg["character_ids"],
                                cfg["location_id"], ticks, be, resume=resume,
                                dm=dm_options, pins=cfg.get("revisions"),
                                memory_from=memory_from
                                or cfg.get("memory_from"))
            cost = None
            if backend != "mock":
                cost = be.collect_total_tokens()
                store.update_run_cost(run_id, cost)
            result = {"run_id": run_id, "event_count": len(events),
                      "ticks": ticks, "cost_tokens": cost}
            if dm:
                calls = store.list_dm_calls(run_id)
                result["dm_calls"] = len(calls)
                result["dm_failed"] = sum(1 for c in calls if c["failed"])
            return result
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

    # ---- 011 US1：读接口（创作 agent 全读路径，零文件中转） ----

    @mcp.tool()
    def list_assets(type: str | None = None) -> dict:
        """列出资产概要（asset_id/type/name/status/current_revision）。
        type 可筛 character/prop/scene/epoch。"""
        store = _store()
        try:
            return {"assets": store.list_asset_summaries(type)}
        finally:
            store.close()

    @mcp.tool()
    def get_asset(asset_id: str) -> dict:
        """读资产完整卡（persona_spec/appearance/provenance/当前修订版号）。
        persona_spec.secret 为创作可见、仿真角色不可见信息。"""
        store = _store()
        try:
            try:
                asset = store.get_asset(asset_id)
            except KeyError:
                raise ToolError(f"AssetNotFound: 资产 {asset_id} 不存在")
            asset["current_revision"] = store.current_revision(asset_id)
            asset["secrecy"] = ("persona_spec.secret：创作可见，"
                                "仿真中其他角色不可见")
            return asset
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def get_materials(asset_id: str) -> dict:
        """读资产的调研原料（query/retriever/context/created_at）。"""
        store = _store()
        try:
            return {"materials": store.get_materials(asset_id)}
        finally:
            store.close()

    @mcp.tool()
    def search_materials(keyword: str) -> dict:
        """原料关键词检索（query/context 子串，大小写不敏感）。"""
        store = _store()
        try:
            return {"materials": store.search_materials(keyword)}
        finally:
            store.close()

    @mcp.tool()
    def get_events(run_id: str) -> dict:
        """直接返回某次 run 的事件列表（与 export_events 文件同口径）。"""
        store = _store()
        try:
            if not store.run_exists(run_id):
                raise ToolError(f"RunNotFound: run {run_id} 不存在")
            return {"events": store.export_events(run_id)}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def get_world_state(world_id: str) -> dict:
        """读世界最新快照 {tick, state}；无快照返回 {tick: None, state: None}。"""
        store = _store()
        try:
            if store.get_world_config(world_id) is None:
                raise ToolError(f"WorldNotFound: world {world_id} 不存在")
            saved = store.get_world_state(world_id)
            if saved is None:
                return {"tick": None, "state": None}
            tick, state_json = saved
            return {"tick": tick, "state": json.loads(state_json)}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def list_dm_calls(run_id: str) -> dict:
        """读某次 run 的裁决台账（010 dm_calls 全字段）。"""
        store = _store()
        try:
            if not store.run_exists(run_id):
                raise ToolError(f"RunNotFound: run {run_id} 不存在")
            return {"dm_calls": store.list_dm_calls(run_id)}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    # ---- 011 US2：修订与回滚 ----

    @mcp.tool()
    def revise_asset(asset_id: str, patch: dict, reason: str,
                     author: str = "creation-agent",
                     base_revision: int | None = None) -> dict:
        """修订资产（merge patch 深合并，值 None 删键）存为新版本。
        base_revision 乐观锁：与当前版不符返回 RevisionConflict。
        返回 {asset_id, revision, impacted, warning}——impacted 列出引用过
        旧版的世界/run（修订不改历史，重拍或新建世界才用新版）。"""
        from .revision import revise
        store = _store()
        try:
            try:
                return revise(store, asset_id, patch, reason, author,
                              base_revision)
            except KeyError:
                raise ToolError(f"AssetNotFound: 资产 {asset_id} 不存在")
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def rollback_asset(asset_id: str, to_revision: int) -> dict:
        """回滚资产到指定修订版（历史保留，仅移动当前指针）。
        返回 {asset_id, current_revision, stale_worlds}——stale_worlds 为
        冻结了更高版号的世界（数据不变，仅标记）。"""
        from .revision import rollback
        store = _store()
        try:
            try:
                return rollback(store, asset_id, to_revision)
            except KeyError:
                raise ToolError(f"AssetNotFound: 资产 {asset_id} 不存在")
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    # ---- 011 US3：移交包 ----

    @mcp.tool()
    def export_handoff(world_id: str, out_dir: str = "handoff",
                       run_id: str | None = None,
                       overwrite: bool = False) -> dict:
        """导出自描述移交目录（manifest + assets + events + world 快照 +
        dm_calls + materials + sources），供创作 agent team 消费。
        目录已存在且 overwrite=False 时拒绝（HandoffExists）。"""
        from .handoff import export_handoff as _export
        store = _store()
        try:
            try:
                return _export(store, world_id, out_dir, run_id, overwrite)
            except KeyError:
                raise ToolError(f"WorldNotFound: world {world_id} 不存在")
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    # ---- 011 FR-014：立项调研 ----

    @mcp.tool()
    def research_brief(theme: str) -> dict:
        """立项调研（009）：题材 → 三类清单 → 批量执行入库（含去重漏斗）。
        返回 {brief, ledger}。注意：每条调研一次外部调用，分钟级耗时，
        按次产生检索与模型成本（宪章 VI）。"""
        from .brief import execute_brief as _execute
        from .brief import generate_brief as _generate
        store = _store()
        try:
            brief = _generate(theme)
            ledger = _execute(brief, store)
            return {"brief": brief, "ledger": ledger}
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    # ---- 011 US4：重拍 ----
    @mcp.tool()
    def reshoot(world_id: str, new_run_id: str, ticks: int,
                use_latest: bool = False, backend: str = "mock",
                dm: bool = False,
                memory_from: str | None = None) -> dict:
        """重拍某世界：use_latest=False 按冻结版号原样重跑；True 把版号
        重钉到各资产当前版（先 revise_asset 再重拍即修订重拍）。
        产出新 run，事件编号全局连续，两版并存可 diff。"""
        store = _store()
        try:
            cfg = store.get_world_config(world_id)
            if cfg is None:
                raise ToolError(f"WorldNotFound: world {world_id} 不存在")
            if store.run_exists(new_run_id):
                raise ToolError(f"RunExists: run {new_run_id} 已存在")
            if use_latest:
                cfg["revisions"] = {
                    aid: store.current_revision(aid)
                    for aid in [*cfg["character_ids"], cfg["location_id"]]}
                store.put_world_config(world_id, json.dumps(
                    cfg, ensure_ascii=False))
            if backend == "mock":
                be = MockPersonaBackend()
            else:
                from .persona_tinytroupe import TinyTroupeBackend
                be = TinyTroupeBackend()
            dm_options = None
            if dm:
                from .world import DMOptions
                dm_options = DMOptions()
            events = _run_world(store, new_run_id, world_id,
                                cfg["character_ids"], cfg["location_id"],
                                ticks, be, dm=dm_options,
                                pins=cfg.get("revisions"),
                                memory_from=memory_from
                                or cfg.get("memory_from"))
            return {"run_id": new_run_id, "event_count": len(events),
                    "revision_pins": cfg.get("revisions") or {}}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    # ---- 012：幕间记忆 ----

    @mcp.tool()
    def generate_interlude_memory(run_id: str, character_ids: list[str],
                                  channel: str = "template",
                                  regenerate: bool = False) -> dict:
        """从指定 run 生成各角色的幕间记忆（按可感知性过滤，私语零泄漏）。
        channel=template（离线确定性）| llm（真实摘要，每角色一次调用）。
        同键已存在且 regenerate=False 时复用（reused=True，零重复计费）。
        未参与来源 run 的角色列入 skipped。"""
        from .interlude import InterludeError, generate_memories
        store = _store()
        try:
            try:
                mems = generate_memories(store, run_id, character_ids,
                                         channel=channel,
                                         regenerate=regenerate)
            except InterludeError as e:
                msg = str(e)
                if msg.startswith("BadChannel"):
                    raise ToolError(msg)
                raise ToolError(f"RunNotFound: {msg}")
            return {"memories": mems,
                    "skipped": [m["asset_id"] for m in mems
                                if m.get("skipped")]}
        except ToolError:
            raise
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    @mcp.tool()
    def get_interlude_memory(run_id: str,
                             asset_id: str | None = None) -> dict:
        """读取幕间记忆（asset_id 缺省取该 run 全部当前版）。"""
        from .interlude import get_memories
        store = _store()
        try:
            return {"memories": get_memories(store, run_id, asset_id)}
        except Exception as e:
            raise _fail(e) from e
        finally:
            store.close()

    return mcp

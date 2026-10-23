# 已知限制（Known Limitations）

本文件列出当前版本**有意保留或尚未解决**的限制。每条写清：症状、影响、绕过办法。
修复任何一条都要独立分支 + 报批，不在文档改动里夹带。

---

## 1. 调研原料 8000 字符硬截断

- **症状**：单条原料最多 8000 字符（`RESEARCH_MATERIAL_MAX_CHARS`），长论文/专著会被切在中途，摘要与正文重复占用额度。
- **影响**：需要后文才能回答的问题可能缺料；多段长文主题容易只取到前半。
- **绕过**：把查询拆成多条更聚焦的词分别调研，按（query + 原料）合并使用；出包前用质检四项（去重率 / 目录类行 / 导航占比 / 是否撞 8000）判定是否废料。

## 2. 素材类原料的 asset_id 共用 slug，归属不清

- **症状**：未指定 `link_asset_id` 的素材类原料统一挂在 `lore:<slug>`（如 `lore:6d3f523f`）下，不同 lore 可能共用同一个 id。
- **影响**：按资产查原料时会混入不同主题的料；无法从 id 反查具体主题。
- **绕过**：调研时显式传 `link_asset_id` 挂到具体资产卡；已入库的 lore 料按 query 区分，不看 id。

## 3. 调研直接写库，没有 dry-run

- **症状**：`research_asset` / `research_brief` / `research_material` 一旦调用就写库（资产 + 原料），没有「只预览不落库」的模式。
- **影响**：查询词选错也会留下资产或原料；清理要手工删库或走 reset 类操作。
- **绕过**：先在库副本上试（`Copy-Item` 后 `--db` 指向副本），验证查询词与质检指标后再动真库；每次写库前确认目标库路径（主库/项目库别混）。

## 4. MCP 调用的客户端超时（实践约 60 秒）

- **症状**：工具调用有客户端请求超时（实践约 60 秒）；超时后调用方拿不到结果，服务端行为不一致（可能继续跑完，也可能中断）。
- **影响**：单次调用无法可靠承载分钟级操作（真实调研、多 tick 仿真、整包导出+搬运）。
- **绕过**：分钟级操作一律走 CLI（`scripts/research_asset.py`、CLI runner 直调 `orchestrator.world.run_world`），不靠 MCP 工具调用；超时后先 `get_world_state` / `get_events` 核对服务端实际进度，不盲目重跑。

## 5. `research_materials` 没有判定列（verdict / note）

- **症状**：原料表只有 query / retriever / context / created_at，没有「采用/废料/豁免」等判定字段。
- **影响**：质检结论无法随原料落库，跨机器/回滚/交接时容易丢；`export_handoff` 也不会带上判定。
- **绕过**：判定落在 `data/asset_notes/<asset_id>.md` 台账文件（随库入库），并在正文引用原料编号；把判定迁进库需要 schema 迁移（单独报批、单独分支）。

## 6. 单角色世界的事件流必然是独白

- **症状**：`create_world` 只有角色与场景参数，**没有道具参数**；单角色世界里角色只能自言自语，台词无人回应。
- **影响**：做不出对手戏；道具（如蜡丸）进不了世界，只能在事件文本里被提及（或作为素材交给编剧）。
- **绕过**：第二集起先补第二个角色（走调研管线），再建世界；单角色事件只当节奏骨架，台词由编剧重写。

## 7. 出图顶修订号时期留下的历史修订号（2026-10-22 前）

- **症状**：旧版 `generate_reference_image` 每出一张图就把资产 payload 的 `reference_images` 追加并升一版，导致部分资产的修订号被图片顶高（如察子项目库 rev13 中大部分只代表出过图）。
- **影响**：看 2026-10-22 22:31 之前的修订号，无法区分「内容改了」还是「出了张图」。
- **绕过**：跨库/跨版本比对用 `content_sha256`（忽略 `reference_images`）；历史修订行按约定保留、不重写；时间窗与受影响资产见 `data/asset_notes/library_vs_project_revisions.md`。

## 8. `asset_port` 不搬运出图台账

- **症状**：`asset_port export/import` 只搬 `assets` / `asset_revisions` / `research_materials` 三张表，不搬 `image_generations`。
- **影响**：资产从主库导到项目库时，参考图记录不会跟着走；项目库的参考图需在项目侧生成/登记。
- **绕过**：把出图当作项目库本地产物（与路径、环境相关）；需要图时在目标库重新出图；`verify` 会把图片差异单列在 `images` 段，不当失败。

## 9. 外部不可安装（内部版本）

- **症状**：依赖 `worldseed[dm]` 来自本机 path（`pyproject.toml`：`worldseed = { path = "D:/kimicode_repos/projects/my_mas/WorldSeed", editable = true }`），且该工作副本带 3 行本地编码补丁（见 `docs/worldseed-local-patch/`）。裸 `pip install narrative-sim` / 干净 runner 无法解析这个 path，装不上。
- **影响**：本项目当前**只能在具备 `my_mas/WorldSeed` 目录并打过该补丁的机器上安装运行**；PyPI 上的 `worldseed` 是**另一个发行版**（0.0.1，只有 `gui` extra，没有 `dm`），**不能替代**。对外发布/协作复现会被卡住；CI 也因此暂不可用。
- **绕过**：复制整个 `my_mas/WorldSeed` 工作副本（含未跟踪的本地文件），按 `docs/worldseed-local-patch/README.md` 打 `locale-encoding.patch`，再在本机 `uv sync`；验证方式是离线测试 `225 passed, 1 deselected`。不要改依赖来源、不要 vendor、不要指到 PyPI 的 `worldseed`。
- **性质**：这是**内部版本**（0.2.0）的既定限制，不是待修 bug；若要对外发布，必须先单独设计 `worldseed` 的可分发来源（独立报批）。

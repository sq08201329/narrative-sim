# data/ —— 数据库与台账

本目录存放全部 SQLite 戏库与配套台账。`*.db`、`*.bak` 是本地产物，不入 git。

## 一、库结构：调研主库 + 项目库

两个库职责严格分离，不要混用。

| 文件 | 角色 | 内容 | 读写规则 |
|------|------|------|----------|
| `data/library.db` | **调研主库** | `assets` / `asset_revisions` / `research_materials`；**0 世界 0 事件** | 调研（`research_asset` / `research_brief`）**只写这里**；资产修订也在这里做 |
| `data/projects/linan.db` | **项目库** | 世界、`runs`、`events`、`dm_calls`，以及本项目世界要用的资产快照 | `NARRATIVE_DB` 指向它；仿真、建世界、出移交包**只用这里** |

铁律：

- **调研只写主库，仿真只用项目库。**
- 一个资产**只在一个库里被修订**：修订在主库做，项目库用导入的固定版本（版号锚点不变）。
- 项目库要用的资产**从主库导入**，见第三节。

## 二、起停：统一走 start_stack.ps1

```powershell
pwsh -File scripts\start_stack.ps1 status    # 看三个服务
pwsh -File scripts\start_stack.ps1 start     # 按固定顺序起
pwsh -File scripts\start_stack.ps1 stop      # 反序停
pwsh -File scripts\start_stack.ps1 restart
```

- 固定顺序：**embedding（9379）→ gptr-mcp（8000）→ narrative-sim（8300）**；停是反序。
- embedding 健康检查 `GET /v1/models`；gptr-mcp 用 `GET /health`；任一不过直接 `exit 1`，后面的不启动。
- 脚本幂等，已在线就跳过；两个/三个服务都 `Start-Process` 起独立进程，shell 关了不受影响。
- **不要再手工拼环境变量起 `run_mcp_server.py`**。
- 端点：embedding `http://127.0.0.1:9379/v1`、gptr-mcp `http://127.0.0.1:8000/mcp`、narrative-sim `http://127.0.0.1:8300/mcp`（22 个工具）。
- 工具数仍用 `scripts\mcp_service.py status` 看（`start_stack.ps1 status` 只看端口与健康检查）。
- **启动脚本在后台跑时别杀启动壳**：`start_stack.ps1 start` 的后台进程壳被杀会带走整个进程树、三服务一起掉；只等端口就绪（9379 / 8000 / 8300）即可。

## 三、跨库搬运：scripts\asset_port.py

```powershell
python scripts\asset_port.py export --db data\library.db --asset-id <id> --out <bundle.json>
python scripts\asset_port.py import --db data\projects\linan.db --file <bundle.json>
python scripts\asset_port.py verify --db data\projects\linan.db --file <bundle.json>
```

- bundle 含：资产行 + **全部** `asset_revisions` + 该资产全部 `research_materials`，逐段 sha256 + 整体 `bundle_sha256`。
- import 保持 `asset_id` 与 revision 号不变；幂等（内容一致整体跳过）；冲突（同号不同内容 / 目标库领先 / 指针不一致）**报错且不覆盖**；`--allow-extend` 才补落后修订。
- `provenance=manual` 的手写资产：export 放行并标记，import **默认拒绝**，`--allow-manual` 才放且打警告。
- 导入只碰 `assets` / `asset_revisions` / `research_materials` 三张表；导入前默认自动备份目标库。
- **不许手工 `Copy-Item` 库文件**——那样会丢原料和 provenance（资产能复制，原料不跟着走）。

## 四、归档目录：data/_legacy/

旧验收/冒烟库、旧真库 `yanyu.db` 及其迁移备份，全部移入 `data/_legacy/`，**只读、不删**：

- `narrative_sim.db`（历史默认测试库）
- `yanyu.db` + `yanyu.db.pre_migration.bak` + `yanyu.db.bak.<时间戳>`
- `world_talk.db` / `world_real.db` / `world_mock.db`
- `dm_accept.db` / `dm_fault.db`
- `research005.db` / `research_accept.db` / `m1_check.db`

逐库说明（是什么、什么时候的、为什么归档）见 `data/_legacy/README.md`。

- `yanyu.db` 已归档，**不要再往它写**。
- 需要恢复某个历史库：复制到 `data/` 之外再操作，不要就地改。

## 五、.env 键名（只列名，不写值）

`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`MODEL_FAST`、`MODEL_SMART`、`MINIMAX_API_KEY`、`GPTR_MCP_URL`、`EMBEDDING_API_BASE`、`EMBEDDING_MODEL`、`NARRATIVE_DB`、`LIBRARY_DB`。

- `NARRATIVE_DB` 指向项目库，服务启动时必须带上（默认库是测试库 `data/narrative_sim.db`，裸起会掉进去）。
- 密钥只经环境变量注入子进程，不打印、不回显、不写文件。

## 六、台账文件：`data/asset_notes/<asset_id>.md`

`research_materials` 表**没有备注字段**，所以原料的质检判定与豁免记录落在文件里，并且**跟库一起入库**（审计记录：哪条判废、哪条豁免、谁批的、为什么——换机器、回滚、交接都不能丢）。

**约定**：

- **每个需要判定的原料**，都要在该资产卡旁写一份 `data/asset_notes/<asset_id>.md`，一卡一份。
- 内容四段：① 卡与验收结论；② 每条原料的 query、质检四项（字符、去重率、目录类行、导航占比、是否撞 8000）与判定（采用 / 废料）；③ 若触发严格门豁免，写明数值、豁免理由、批准人与日期；④ 不再补采的判断依据。
- **判定改了要改文件并留日期，不删旧结论**（追加式修订，保留历史口径）。
- 现有实例：`data/asset_notes/scene_35e0d60739.md`（#10 判废；#11 采用，含 0.792/0.800 严格门豁免与批准人）。

> 将来若要把备注进库（`research_materials` 加 `verdict` / `note` 列），属于 schema 迁移，需单独报批、单独分支，不在文档改动里夹带。

## 七、历史测试库（已归档）

曾经的「演示/验收库」已全部移入 `data/_legacy/`，本目录不再保留：

- 归档说明与逐库清单：`data/_legacy/README.md`（**只读**；要恢复请复制出去再操作）。
- `narrative_sim.db` 是历史的默认测试库，**已归档**，不再是默认工作库。
- 运维注意：`orchestrator/mcp_server.py` 的缺省库路径仍是 `data/narrative_sim.db`——**裸起**服务（不带 `NARRATIVE_DB`）会新建一个空测试库，不是生产线库。起服务一律用 `scripts\start_stack.ps1`（自动带项目库 `data/projects/linan.db`）。

## 八、其他本地产物

- `logs/`：服务日志与 pidfile
- `exports/`：事件 JSONL、搬运 bundle、临时巡检报告
- `images/`：参考图草稿
- `handoff/`：移交包

以上目录与本目录下的 `*.db` / `*.bak` 均已 gitignore。要对外分享数据用 `export_handoff` 出移交包，不要发库文件。

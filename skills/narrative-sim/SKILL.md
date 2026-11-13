---
name: narrative-sim
description: 使用 narrative-sim 进行史料调研、资产库管理、世界创建、多角色仿真、事件导出和 MCP 服务调用。用户要求调研史料、建立叙事世界、运行/续跑仿真、导出剧情事件或管理本地叙事服务时使用。
---

# NarrativeSim 使用技能

本项目只负责调研与仿真，不承担剧本创作。把调研事实、明确标记的私设和仿真事件提供给后续创作流程，不把模型想象写成史料。

## 首次初始化

开发版使用 `uv run narrative`，冻结版把命令替换为 `NarrativeSim.exe`。

```bash
narrative init
```

初始化在用户 HOME 创建配置、数据、日志、缓存和技能目录。已有文件不会覆盖。
冻结版默认 HOME 为 `%LOCALAPPDATA%/NarrativeSim`；开发版默认仓库根目录。
可用 `--home` / `NARRATIVE_HOME` 覆盖。

## 数据库边界

- 调研主库：`<HOME>/data/library.db`，由 `LIBRARY_DB` / `--library-db` 覆盖。
  调研资产、资产修订和原料只写这里。
- 剧目项目库：`<HOME>/data/projects/linan.db`，由 `NARRATIVE_DB` / `--db` 覆盖。
  世界、运行、事件和项目资产快照只写这里。
- 古籍文库：`<HOME>/data/corpus.db`，由 `CORPUS_DB` 覆盖。全部剧目共享，只读检索。

不要把调研写入项目库，也不要把仿真写入调研主库。项目库需要主库资产时，用
`scripts/asset_port.py` 的 export/import 搬运完整修订和原料，不直接复制 SQLite 文件。

## 服务管理

```bash
narrative start
narrative status
narrative stop
narrative restart
```

启动顺序为嵌入服务 → 调研 MCP → 叙事 MCP。健康的外部服务可复用；stop 只停止
受管进程。真实调研需要 DeepSeek 凭据和网络；本地嵌入需要 LiteRT-LM 与量化模型。
密钥只放用户 `.env` 或环境变量，不写入技能、日志、代码或命令参数。

## 典型工作流

### 1. 调研资产

```bash
narrative research "南宋临安众安桥附近的酒楼形制" --type scene
```

类型为 `character / prop / scene / epoch`。记录返回的 asset_id 和来源；史料缺失的人物
年龄、家庭、摊位等不得自动当作史实。

### 2. 准备项目资产

从调研主库导出资产包，再导入当前项目库：

```bash
python scripts/asset_port.py export --db <主库> --asset-id <ID> --out <bundle.json>
python scripts/asset_port.py import --db <项目库> --file <bundle.json>
```

冻结环境没有 Python 时，应由发行版提供资产搬运命令后使用；在此之前保留开发工具完成
该步骤，不用数据库整文件复制替代。

### 3. 创建世界并仿真

```bash
narrative world create W001 --characters char_001,char_002 --location scene_001
narrative run W001 --run-id R001 --ticks 4 --backend mock
```

真实角色后端使用 `--backend tinytroupe`；需要裁决时加 `--dm`。续跑加 `--resume`，
幕间记忆可用 `--memory-from <上一幕run_id>`。世界创建会冻结资产修订，后续修订不自动
污染已经创建的世界。

### 4. 导出

```bash
narrative export R001 --out <HOME>/exports/R001.jsonl
```

每行一个契约事件。视频或创作消费者只通过 asset_id 引用资产，不在事件中内联外貌文本。

## MCP

前台启动：

```bash
narrative mcp --transport streamable-http
# stdio 客户端：narrative mcp --transport stdio
```

默认 HTTP 地址由 `MCP_HOST` / `MCP_PORT` 决定。MCP 工具包括调研、世界、仿真、导出、
资产读取/修订、原料、事件、记忆、移交、参考图和古籍检索。优先复用现有工具，不直接
操作数据库。stdio 的 stdout 只承载协议，日志不得写入该通道。

## 安全与质量

- 失败命令会返回非零；不要根据部分输出假定成功。
- 真实调研必须有来源；无来源或契约校验失败不得入库。
- 仿真内容需要人工复核后才能用于正式产出。
- 不删除或覆盖用户数据库，不停止未知进程，不把测试数据写入正式主库。

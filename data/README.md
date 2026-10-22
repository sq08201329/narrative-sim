# data/ —— 数据库文件台账

全部 SQLite 戏库统一放这里（`*.db` 已被 .gitignore 排除，属本地产物）。
默认库为 `data/narrative_sim.db`（MCP server 与各 CLI 的缺省）。

## 演示/验收库一览

| 文件 | 来源特性 | 内容 |
|------|----------|------|
| `yanyu.db` | 009 立项调研 | 皇城司题材：3 资产（察子/临安街巷/蜡丸）+ 调研原料；013 有一张内部草稿图登记 |
| `world_talk.db` | 008/012 | 沈刻×苏晚晴对手戏 run talk_r1（14 事件真对白）+ 第二幕 talk_r2（带幕间记忆）+ llm 记忆 2 条 |
| `dm_accept.db` | 010 验收 | DM 裁决 run（dm_r1 真后端 / dm_r3 mock+真裁决 4 调用） |
| `dm_fault.db` | 010 验收 | 裁决服务故障注入 run（降级 100% 完成证据） |
| `world_real.db` | 006 验收 | WorldSeed 引擎真机 run（9 事件） |
| `world_mock.db` | 006 冒烟 | mock 后端世界链路 |
| `research005.db` / `research_accept.db` | 004/005 验收 | 调研管线资产 |
| `m1_check.db` | 001 验收 | 最小链路 |
| `narrative_sim.db` | 默认工作库 | MCP server 缺省挂载 |

## 规矩

- 新库一律放这里，用 `--db data/xxx.db` 或 `NARRATIVE_DB=data/xxx.db`
- 库是本地二进制产物，不入 git；要分享用 011 的 `export_handoff` 出移交包
- `logs/`（服务日志与 pidfile）、`exports/`（事件 JSONL）、`images/`（参考图草稿）、`handoff/`（移交包）同为本地目录，均已 gitignore

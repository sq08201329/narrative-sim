# Data Model: 统一 CLI 应用

本特性不改变资产、事件、世界或运行的持久化模型，仅增加命令与服务运行视图。

## CommandResult

| 字段 | 含义 | 校验规则 |
|---|---|---|
| action | 已执行命令 | 与请求命令一致 |
| 业务字段 | asset_id / world_id / run_id / path 等 | 复用现有业务标识与契约 |
| services | 服务状态数组 | 仅服务管理命令返回 |

结果以 JSON 写 stdout；失败不写成功结果，诊断写 stderr，退出状态非零。

## ServiceStatus

| 字段 | 含义 | 校验规则 |
|---|---|---|
| name | embedding / gptr-mcp / narrative-sim | 固定三项 |
| state | ready / stopped / unhealthy / external | ready 必须通过对应健康检查 |
| pid | 监听器或受管进程 PID | 可为空；不得据此单独判定所有权 |
| managed | 是否由当前 CLI 状态管理 | 只有 PID、创建时间和命令行均匹配才为 true |
| port | 服务端口 | 使用配置值 |
| log | 日志路径 | 位于统一日志目录 |

### 状态判定

- `stopped`：无健康服务且无受管存活进程。
- `ready`：受管进程存活且健康检查通过。
- `external`：健康检查通过但无匹配的受管进程；启动可复用，停止必须跳过。
- `unhealthy`：进程或端口存在但健康检查失败，或状态文件过期/冲突。

## ManagedServiceRecord

由 `orchestrator/services.py` 独占读写，保存于 `<NARRATIVE_HOME>/run/`。

| 字段 | 含义 | 校验规则 |
|---|---|---|
| name | 服务名 | 固定三项之一 |
| pid | 启动进程 PID | 正整数 |
| created | 进程创建时间 | 与 psutil 当前值匹配才允许终止 |
| command | 启动命令数组 | 必须包含该服务预期标识 |
| log |  stdout/stderr 日志路径 | 不含密钥内容 |

状态写入必须原子替换；过期文件可清理但不得直接终止进程。该记录不是世界状态，不参与断点续跑。

## ApplicationPaths

| 字段 | 来源优先级 | 默认值 |
|---|---|---|
| home | `--home` → `NARRATIVE_HOME` | 项目根目录 |
| database | `--db` → `NARRATIVE_DB` | `<home>/data/projects/linan.db`；世界、仿真和导出 |
| library_database | `--library-db` → `LIBRARY_DB` | `<home>/data/library.db`；仅供 research |
| logs | 由 home 派生 | `<home>/logs` |
| runtime | 由 home 派生 | `<home>/run` |

所有路径在命令开始时解析为绝对路径；目录按需创建，不覆盖既有数据库。

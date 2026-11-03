# Data Model: Windows 独立应用

不修改业务数据库，仅定义发行与冻结路径。

## DistributionLayout

```text
NarrativeSim/
├─ NarrativeSim.exe
├─ _internal/          # Python、依赖与只读运行资源
├─ README.md
├─ BUILD-INFO.json
└─ licenses/
```

ZIP 必须只有 `NarrativeSim/` 一个顶层目录。构建信息包含应用版本、PyInstaller 版本、目标平台和构建时间，不包含环境变量值或密钥。

## FrozenUserHome

默认：`%LOCALAPPDATA%/NarrativeSim`；`NARRATIVE_HOME` 或 `--home` 可覆盖。

```text
<HOME>/
├─ .env                 # 用户自行准备，不由构建提供
├─ config.ini           # 首次由只读默认模板复制，之后不覆盖
├─ data/
│  ├─ projects/linan.db
│  ├─ library.db
│  └─ corpus.db
├─ logs/
├─ run/
└─ exports/
```

开发模式 HOME 仍为仓库根。路径覆盖优先级沿用 019；修改 HOME 不迁移旧数据。

## FrozenProcess

| 服务 | 冻结启动方式 | 所有权标识 |
|---|---|---|
| narrative-sim | `NarrativeSim.exe ... mcp` | orchestrator.cli |
| gptr-mcp | `NarrativeSim.exe _gptr` | `_gptr` 与 PID/创建时间 |
| embedding | 配置的 LiteRT-LM | 既有 litert-lm 标识 |

冻结进程不得使用 `python`/`uv` 作为启动命令。stdout 协议、日志重定向和进程终止规则沿用现有实现。

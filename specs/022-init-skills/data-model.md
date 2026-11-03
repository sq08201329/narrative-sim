# Data Model: 初始化与使用技能分发

不修改业务数据库。

## InitResult

| 字段 | 含义 |
|---|---|
| home | 用户目录绝对路径 |
| directories | 各目录 path 与 created/existing |
| files | config.ini、.env、SKILL.md 的 path 与 created/existing |

目录至少包括：`data/`、`logs/`、`run/`、`models/`、`cache/`、`skills/`。
文件目标为 `config.ini`、`.env`、`skills/narrative-sim/SKILL.md`。

已有目标必须保留原字节并报告 existing；缺失模板或写入失败返回非零，不输出成功结果。

## 资源来源

- config.ini：既有运行配置模板。
- .env：`.env.example`，不含真实密钥。
- SKILL.md：`resources/skills/narrative-sim/SKILL.md`，开发与冻结共用。

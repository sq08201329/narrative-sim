# Contract: 真后端链路 CLI

## 命令

```bash
uv run python scripts/run_real_chain.py
```

cwd 必须是项目根目录（TinyTroupe 读 `./config.ini`）。

## 前置条件

- `uv sync` 已执行（tinytroupe 依赖已按锁文件安装）
- `.env` 含有效 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL`
- 网络可访问 DeepSeek 服务

## 行为契约

与 `run_minimal_chain.py` 同构，唯一差异是后端注入为 `TinyTroupeBackend`：

1. 校验 cwd 与环境变量，缺失即明确报错（退出码非 0）
2. 幂等初始化数据库；同名 run 存在时显式重置
3. 入库示例角色与场景资产（契约校验）
4. 真后端运行 4 回合仿真
5. 导出事件流 JSONL 并逐条复验契约
6. 写入本次运行的 token 成本
7. 末行输出 `验收通过`

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | ≥5 条事件全部通过契约校验，成本已落库 |
| 非 0 | 前置校验失败 / LLM 终极失败 / 契约校验失败；stderr 指明环节 |

## 与 Mock 链路的关系

两脚本差异只允许出现在后端注入参数；Mock 链路在无密钥环境照常通过
（FR-005 / US2 AC2）。

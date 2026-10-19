# Quickstart: uv 项目脚手架与最小仿真链路（M1）基线

端到端验证本特性"能用"的最短路径。命令在仓库根目录执行
（PowerShell 与 Git Bash 相同）。

## 前置

- 已安装 uv（`uv --version` 可用）
- 本仓库的干净检出

## 三步验证（对应 spec SC-001）

```bash
uv sync                                    # 1. 装依赖（生成 .venv，读 uv.lock）
cp .env.example .env                       # 2. 准备环境变量模板（M1 无需填值）
uv run python scripts/run_minimal_chain.py # 3. 跑最小链路
```

**期望**：最后一行输出 `验收通过`，退出码 0；`exports/` 下生成事件流 JSONL。

详见 [contracts/cli-minimal-chain.md](contracts/cli-minimal-chain.md)。

## 验证确定性（对应 spec SC-002）

```bash
uv run python scripts/run_minimal_chain.py   # 再跑一次
```

**期望**：两次导出的 JSONL 除 `created_at` 外逐字节一致。

## 验证契约守卫（对应 spec SC-003）

```bash
uv run pytest tests/ -q
```

**期望**：全部用例通过，覆盖：

- 非法资产（缺必填字段 / asset_id 格式不符）入库被拒
- 非法事件写入被拒
- 最小链路全绿且离线运行

## 验证接缝（对应 spec SC-005）

- 角色后端：`scripts/run_minimal_chain.py` 中 Mock 后端为注入参数，
  可替换为任何满足同一接口的实现（见 [data-model.md](data-model.md) 与
  [contracts/asset-event-schemas.md](contracts/asset-event-schemas.md)）
- 存储：`tests/` 中不存在第二条数据库通路
- 导出：`exports/*.jsonl` 可脱离数据库逐行解析

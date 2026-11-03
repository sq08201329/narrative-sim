# Quickstart: Windows 独立应用

## 构建

```bash
uv sync
uv run python scripts/build_standalone.py
```

预期生成 `dist/NarrativeSim/NarrativeSim.exe` 与 `dist/NarrativeSim-windows-x64.zip`；构建日志无真实密钥，产物不含数据库、模型、日志或 `.env`。

## 冻结离线链路

将 `dist/NarrativeSim` 复制到新的中文且含空格目录。设置临时 `NARRATIVE_HOME`，仅调用复制后的 EXE：

```powershell
NarrativeSim.exe --help
NarrativeSim.exe world create ...   # 使用验收夹具准备的项目库
NarrativeSim.exe run ... --ticks 4 --backend mock
NarrativeSim.exe export ... --out <HOME>/exports/events.jsonl
```

预期至少 5 条契约事件；进程命令行不出现系统 Python/uv；用户文件全部在 HOME。

## MCP 与服务

1. 以 EXE 启动 stdio MCP，用现有客户端列工具并读取资产。
2. 以 EXE 启动 HTTP MCP 并健康检查，停止后端口释放。
3. 用内部 `_gptr` 验证调研服务启动/健康/停止，不发起真实调研。
4. 缺失 LiteRT-LM 或模型文件时，错误包含对应配置名；离线命令不受影响。

## 开发回归

```bash
uv run pytest -q -m "not real"
uv run python scripts/run_minimal_chain.py
```

预期全部通过。验收完成后删除临时发行副本和用户 HOME。

# Distribution Contract

## 公开命令

冻结 EXE 的公开命令、参数、JSON 输出和退出码与 `narrative` 完全一致：

```text
NarrativeSim.exe start|stop|restart|status
NarrativeSim.exe research ...
NarrativeSim.exe world create ...
NarrativeSim.exe run ...
NarrativeSim.exe export ...
NarrativeSim.exe mcp ...
```

`_gptr` 是仅供服务管理器使用的内部命令，不作为公开创作接口。

## 资源与用户文件

发行目录可整体移动，默认不写用户数据。`config.ini` 只在用户目录不存在时复制，升级不得覆盖用户修改。模型、数据库、真实 `.env`、日志和虚拟环境不得进入构建上下文产物。

## 构建入口

```bash
uv run python scripts/build_standalone.py
```

产物：

```text
dist/NarrativeSim/NarrativeSim.exe
dist/NarrativeSim-windows-x64.zip
```

重复构建使用 PyInstaller `--noconfirm` 清理同名旧产物；不得清理其他目录。ZIP 单顶层目录为 `NarrativeSim/`。

## 验收底线

构建成功不等于验收成功。必须实际执行冻结 EXE 的离线全链、MCP 初始化和受管子进程检查；任一动态资源缺失都阻止交付。

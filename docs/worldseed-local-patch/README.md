# worldseed 本地补丁（locale / encoding）

narrative-sim 的引擎依赖 `worldseed[dm]` 来自**本机 path**（见仓库根 `pyproject.toml`）：

```toml
worldseed = { path = "D:/kimicode_repos/projects/my_mas/WorldSeed", editable = true }
```

那份 WorldSeed 工作副本上有 3 行未提交的本地修复，用于 Windows 中文环境。
本目录把补丁原样留档，**防止目录丢失后构建无法复现**。这不是改依赖来源，也不打算上游化。

## 文件

- `locale-encoding.patch` —— `git diff` 原样导出（UTF-8，无 BOM），共 2 个文件 3 行。

## 基线

- 仓库：`D:/kimicode_repos/projects/my_mas/WorldSeed`
- 基线提交：`4ffeabf`（"Update issue templates"）
- 补丁基于该提交的干净工作树导出；`git apply --check --reverse` 在已打补丁的工作树上通过。

## 改了什么（3 行，全部是显式 UTF-8）

1. `src/worldseed/dm/prompt.py`
   `Path(.../shared/languages.json).read_text()` → `read_text(encoding="utf-8")`
2. `src/worldseed/scene/config.py`
   `path.open()` → `path.open(encoding="utf-8")`（`load_config`）
3. `src/worldseed/scene/config.py`
   `preset_path.open()` → `preset_path.open(encoding="utf-8")`（`_resolve_presets`）

`inject_prompt` 会读 `languages.json`，场景加载会读 YAML preset；Windows 默认编码是 GBK，
文件里有中文时会 `UnicodeDecodeError`。这三行是中文配置跑通的**必需修复**。

## 怎么打

```powershell
cd D:\kimicode_repos\projects\my_mas\WorldSeed
git apply D:\kimicode_repos\projects\narrative-sim\docs\worldseed-local-patch\locale-encoding.patch
```

或（没有 git 时）：

```powershell
cd D:\kimicode_repos\projects\my_mas\WorldSeed
patch -p1 < D:\kimicode_repos\projects\narrative-sim\docs\worldseed-local-patch\locale-encoding.patch
```

## 怎么核对

```powershell
git -C D:\kimicode_repos\projects\my_mas\WorldSeed status --short
# 期望：M src/worldseed/dm/prompt.py
#       M src/worldseed/scene/config.py
git -C D:\kimicode_repos\projects\my_mas\WorldSeed diff --stat
# 期望：2 files changed, 3 insertions(+), 3 deletions(-)
```

再把 narrative-sim 的离线测试跑一遍（`uv run --no-sync python -m pytest tests -q -m "not real"`），
期望 `225 passed, 1 deselected`。

## 注意

- WorldSeed 的完整工作副本还有其它未跟踪文件（`.aoci/`、`AGENTS.md`、`mydocs/` 等），
  **不在本补丁范围内**，本补丁只包含上面 3 行。
- 换机器时：复制整个 WorldSeed 目录（保留未跟踪/本地文件），再按上文打补丁；
  只打补丁而不带其余本地文件，可能仍与这台机器的构建有差异。
- PyPI 上的 `worldseed` 是**另一个发行版**（0.0.1，只有 `gui` extra，没有 `dm`），不能替代。

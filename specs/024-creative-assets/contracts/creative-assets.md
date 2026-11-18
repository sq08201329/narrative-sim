# Contracts: 创作资产管理技能

## 技能文件：`skills/creative-assets/SKILL.md` / `<HOME>/skills/creative-assets/SKILL.md`

```yaml
---
name: creative-assets
description: 创作团队基于故事时间树管理素材资产与工作目录。用户要求按节点整理素材、给节点目录命名、管理资产归属或维护创作工作目录时使用。
---
```

内容六节：资产来源 / 资产编号 / 归属 / 物理布局（含工作目录与命名规则）/ 改版与重拍 / 移交。
触发边界：本技能管「创作侧资产与目录」；`narrative-sim` 技能管「调研与仿真工具操作」。

## init

```text
narrative init
NarrativeSim.exe init
```

结构化结果 files 列表新增 `skills/creative-assets/SKILL.md` 的 `{path, status}`，status ∈ created/existing。已有文件不覆盖；模板缺失时明确失败。不启动服务、不下载模型、不改数据库。

## 移交包：`export_handoff`

移交包根新增 `WORKDIR.md`：

```text
<out_dir>/<world_id>/
├── manifest.json
├── WORKDIR.md          # 新增：工作目录规范（采样 assets 之外）
├── assets/
├── events.jsonl
├── world.json
├── dm_calls.json
├── materials/
└── sources.md
```

- `WORKDIR.md` 经 `_write` 写入，计入 `manifest.items`，kind=`workdir`，带 sha256/bytes。
- `manifest.counts` 保持 `{assets, events, dm_calls, materials, images}`，不新增键。
- 既有 `HandoffExists`、`overwrite=True`、无 run 空集行为不变。
- MCP `export_handoff(world_id, out_dir, ...)` 参数与返回结构不变。

## WORKDIR.md 同源文本

位置 `resources/skills/creative-assets/WORKDIR.md`。技能「物理布局 + 归属」两节与其保持一致；创作团队拿到移交包即可据此组织目录，无需先 init。

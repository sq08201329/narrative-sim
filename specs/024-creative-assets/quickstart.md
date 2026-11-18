# Quickstart: 创作资产管理技能

## init 分发

```bash
uv run narrative --home .skill-check init
cat .skill-check/skills/creative-assets/SKILL.md | head -5
uv run narrative --home .skill-check init
```

首次创建技能，状态 created；修改该文件后重复 init，内容不变且状态 existing。确认 frontmatter name=`creative-assets`、description 写明创作侧资产管理。

## 创作团队使用

阅读 `creative-assets` 技能，确认六节齐全；按「物理布局」一节建目录：
全局资产区按 asset_id 存放，节点目录只放 node.json 引用与派生物。核对三条铁律写在技能中。

## 移交包

```bash
# 通过 MCP 或已有链路导出移交包后
ls <out_dir>/<world_id>/WORKDIR.md
python -c "import json; m=json.load(open('<out_dir>/<world_id>/manifest.json')); print([i for i in m['items'] if i['kind']=='workdir'])"
```

WORKDIR.md 存在且被 manifest 记录、sha256 与文件实算一致；counts 键集合不变。

## 回归

```bash
uv run pytest -q -m "not real"
uv run python scripts/run_minimal_chain.py
```

M1 末行仍为「验收通过」；init、handoff、MCP 与技能测试全通过。

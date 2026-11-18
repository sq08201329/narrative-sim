# Data Model: 创作资产管理技能

本特性不修改业务数据库、不新增 schema、不新增存储域。以下描述的是**文档约定实体**（写入技能/WORKDIR.md 的规范内容），非代码实现结构。

## 创作资产技能（SKILL.md）

| 字段 | 含义 |
|---|---|
| name | `creative-assets` |
| description | 创作团队基于时间树管理素材资产与工作目录 |
| 六节正文 | 资产来源 / 资产编号 / 归属 / 物理布局 / 改版与重拍 / 移交 |
| 三条铁律 | node_id 稳定键、ord 全项目唯一、资产本体只引用不复制 |

三处落地：仓库副本（可编辑）、`resources/` 只读模板（init/冻结源）、HOME 副本（init 目标）。已有文件不覆盖。

## 工作目录布局（规范内容）

```text
<项目根>/
├── 00_时间树/T001.json + T001-自查.md
├── 01_节点/N0001_午后_临安酒楼/{node.json, 原文.md, 派生/}
├── 02_角色/<asset_id>/
├── 03_场景/<asset_id>/
├── 04_道具/<asset_id>/
└── 90_移交包/<world_id>/
```

- 节点目录命名 `N{ord:04d}_{text_time或顺位}_{地点/事件短名}`；node_id 是稳定键，后缀仅显示。
- 全局资产区按 asset_id 唯一存放；节点目录只放 node.json（asset_id 引用清单）与派生物。
- 派生物（裁切图、选中参考图、分镜草稿）无 asset_id，留节点目录 `派生/`。

## 资产归属字段（规范约定，非 schema）

| 字段 | 含义 |
|---|---|
| asset_id | `char_/scene/prop_` + 名称 hash，符合契约 `[a-z0-9_]` pattern |
| first_seen_node | 首次登场 node_id；后续节点只加引用不改此值 |
| 来源 | 调研管线 / 手工新建 / 外部素材；手工新建须标注，不伪造 provenance |
| 派生物 | 无 asset_id，随节点目录，不进全局区 |
| 游离资产 | first_seen_node 留空，全局存放，用到时补挂 |

## WORKDIR.md（移交包内）

| 字段 | 含义 |
|---|---|
| 位置 | `<out_dir>/<world_id>/WORKDIR.md` |
| 内容 | 与技能「物理布局 + 归属」两节同源的静态文本 |
| manifest | 经 `_write` 计入 items，带 sha256 / bytes / kind=`workdir` |
| counts | 不新增键，保持既有口径不变 |

## init 结果扩展

`initialize()` 的 files 列表新增一条：`skills/creative-assets/SKILL.md` 的 path 与 created/existing 状态。既有目录/模板行为不变。

# Data Model: 故事时间树

实体存项目库 `linan.db`（戏库同一存储域），全部经 `orchestrator/store.py` 读写。契约见 `contracts/story-tree.md` 与 `schemas/story_tree.schema.json`。

## StoryTree（表 `story_trees`）

| 字段 | 含义 |
|---|---|
| tree_id | 主键，形如 `T001` |
| payload | 通过 schema 校验的完整树 JSON（含 nodes / entities / self_check） |
| source_sha256 | 原文 SHA-256，用于核对 import 来源 |
| status | `ready`（仅自查通过后写入） |
| created_at / checked_at | 创建与自查时间 |

`tree_exists` / `get_tree` / `put_tree` / `list_trees` 为唯一入口；重复 tree_id 默认拒绝，`overwrite=True` 才替换。

## TreeNode（表 `story_nodes`）

| 字段 | 含义 |
|---|---|
| tree_id, node_id | 联合主键，node_id 形如 `n0001` |
| ord | 节点顺序序号（单调递增） |
| payload | 节点 JSON |

`list_tree_nodes(tree_id)` 按 ord 返回；导出与查询以该顺序为准。

## 节点字段

| 字段 | 含义 |
|---|---|
| node_id / ord / parent_node_id | 标识、顺序、父节点（首节点父为 null） |
| text_time | 文本时间（可空，无时间词时用 ord 作锚点，不得编造） |
| location_key | 空间实体 key（对应 scene） |
| character_keys / prop_keys | 人物/道具实体 key 列表 |
| event.type / event.summary | 事件类型与原文摘要（只整理已有事实） |
| source_span | `{start, end, quote}`，原文字符偏移与逐字原文 |

## Entity（去重注册）

| 字段 | 含义 |
|---|---|
| key | 形如 `char_xxx` / `scene_xxx` / `prop_xxx`，符合 asset_id pattern，供后续锚定 |
| type | `character` / `scene` / `prop` |
| name | 去空白/规范化后的规范名，用于调研 query 与去重判定 |

同一规范名只在 entities 出现一次；节点通过 key 引用。自查项「去重」即校验 key/name 唯一且节点引用都能解析。

## SelfCheckReport

| 字段 | 含义 |
|---|---|
| passed | 四项全过为 true |
| checks | `[{name, passed, detail}]`，name ∈ schema / source_span / order / dedup |
| failures | 失败项列表（节点 id + 检查名 + 原因） |
| checked_at | 自查时间 |

四项全部通过才置 `status=ready` 并写库；任一失败自动重试一次，仍失败则非零退出、不写库。

## AssetMap / NodeContext（drive 阶段回填，存 tree payload 扩展字段）

- `entity_assets`: `{entity_key: asset_id}`，research 阶段由 ledger 回填。
- `node_worlds`: `{node_id: world_id}`，world 阶段按空间节点建世界后回填；world_id 形如 `{base}__{node_id}`。
- `run_nodes`: `{run_id: [node_id,...]}`，run 阶段记录锚定关系；多世界时每个 world 派生 run_id `{base}__{node_id}`。

## 状态转换

`import → (自查失败重试→失败: 不写库) → ready`；`ready → research → world → run → export`。未 ready 的树不可 drive（FR-009）。

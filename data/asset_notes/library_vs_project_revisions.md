# 两库修订号差异说明（库级台账，非单资产）

- 记录日期：2026-10-22（2026-10-22 22:31 增补 A1/B1 落地与迁移记录）
- 适用：`data/library.db`（调研主库，内容权威） ↔ `data/projects/linan.db`（项目库）

## 现象（实测）

逐字段比对结论：**唯一差异是 `reference_images`**，审设/外观/provenance 全部一致。

| 资产 | 主库 revision | 主库 reference_images | 项目库 revision | 项目库 reference_images |
|---|---|---|---|---|
| `char_e8301d6530` 察子 | rev1 | 1 条 | rev13 | 13 条 |
| `char_f2a9f87e4c` 刘七郎 | rev0 | 0 条 | rev2 | 2 条 |
| `prop_1a5efe109f` 蜡丸 | rev0 | — | rev0 | — |
| `scene_8e49384273` 旧地图 | rev0 | — | rev0 | — |
| `scene_35e0d60739` 新场景 | rev0 | 0 条 | 已导入 rev0（后出图至 rev3） | 3 条 |

## 原因

`generate_reference_image` 每出一张参考图，就往 asset payload 的 `reference_images` 追加一条并升一小版。
所以项目库高出来的修订号是**出图副作用**，不是内容修订。出图记录本身另有 `image_generations` 表。

## 图片顶修订号的时间窗（历史污染范围）

- 起点：**2026-10-21T13:07:10Z**（本地 2026-10-21 21:07，察子首次出图升版）
- 终点：**2026-10-22T14:00:16Z**（本地 2026-10-22 22:00，新场景最后一次出图）
- A1 落地时间：**2026-10-22 22:31（本地）**，此后出图不再顶修订号
- 窗口内受影响资产：`char_e8301d6530`（proj rev1→13，13 张）、`char_f2a9f87e4c`（proj rev1→2，2 张）、`scene_35e0d60739`（proj rev1→3，3 张）、`char_e8301d6530` 在主库的 rev1（1 张，历史遗留）
- 这些"被图片顶出来的修订号"**作为历史保留、不重写**。看 2026-10-22 22:31 之前的修订号时，要记得它可能只代表出过一张图。

## 比对口径（跨库必读）

- 跨库比对资产时，**只比「除 `reference_images` 之外的字段」**；实现上是 `content_sha256`（payload 剔除该字段后的 canonical JSON 哈希，与 `payload_sha256` 同一套 `sort_keys=True, ensure_ascii=False` 规则）。
- 修订号差异**不当作内容分歧**。
- **禁止反向同步**（项目库 → 主库）：主库是内容权威，这条不变。

## A1 / B1 落地后的语义（2026-10-22）

- **A1**：出图只写 `image_generations`，不再改资产 payload、不升修订；`reference_images` 改为 `Store.get_asset()` 读取时从 `image_generations` **派生**（按 `(created_at, sha256, path)` 稳定排序、按 path 去重，结构仍是相对路径字符串数组）。`revise` / `rollback` / `import_asset_row` / `upsert_revision_at` 都不会把该字段写回当前 payload。
- **B1**：`asset_port` 跨库比对用 `content_sha256`；目标库修订号更高但内容一致 → `identical_content`（不写资产、只补原料），不再误判为 `DstAhead`；真内容分歧仍拒。`verify` 把 `reference_images` 差异单列在 `images` 段，**不算失败**；老 bundle 无 `content_sha256` 时回退旧口径并告警。

## 迁移记录（2026-10-22 22:30:58）

- 只剥离**当前** `assets.payload` 的 `reference_images`；`asset_revisions` 历史行**原样保留**（历史记录不是脏数据）。
- 剥离前后**修订号不变**：察子 lib r1 / proj r13、刘七郎 proj r2、scene_35e0d60739 proj r3、蜡丸 r0、旧地图 r0。
- 迁移前整库备份：
  - `data/library.db.pre_refimg_strip.20261022223058.bak`
  - `data/projects/linan.db.pre_refimg_strip.20261022223058.bak`
  - （另有一次 22:30:44 的半程备份 `library.db.pre_refimg_strip.20261022223044.bak`：撞到 `prop_1a5efe109f` 缺修订行中断，未改项目库，随后修复重跑）
- 顺带补建：`prop_1a5efe109f` 在**两个库**都缺修订行（011 前存量资产），迁移时用 `ensure_revision0` 补建 revision 0；主库 `prop` / `scene_8e49384273` 因此现在可被 `asset_port` 正常导出。
- 迁移后派生结果：库 `char_e8301d6530` 1 张；项目库 `char_e8301d6530` 13 张、`char_f2a9f87e4c` 2 张、`scene_35e0d60739` 3 张。
- 迁移后服务已按新代码重启；`get_world_state` tick 6、`run_linan_ep01_full` 14 条事件不变。

# Data Model: 角色参考图生成

**Date**: 2026-10-21 | **Feature**: 013-reference-images

## 新增表：image_generations（db/init_db.py）

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | |
| asset_id | TEXT NOT NULL REFERENCES assets(asset_id) | |
| prompt | TEXT NOT NULL | 实际使用的提示词（留痕可对照） |
| n | INTEGER NOT NULL | 本次张数（= 计费次数） |
| aspect_ratio | TEXT NOT NULL | 实际宽高比 |
| paths | TEXT NOT NULL | 相对路径列表 JSON |
| sha256 | TEXT NOT NULL | 各文件哈希列表 JSON（与 paths 对齐） |
| provider | TEXT NOT NULL | 图源标识（如 "minimax/image-01"） |
| asset_revision | INTEGER NOT NULL | 变更后的资产修订版号 |
| created_at | TEXT NOT NULL DEFAULT (datetime('now')) | |

索引：`idx_image_gen_asset ON image_generations(asset_id)`。

## 文件布局（不落库）

```text
images/<asset_id>/<sha256[:12]>.png
```

`reference_images`（assets.payload 内既有字段）登记相对路径
（`images/<asset_id>/<sha12>.png`）。

## 宽高比默认（FR-007）

| 资产类型 | 默认 |
|----------|------|
| character / prop | 2:3（竖版） |
| scene / epoch | 16:9（横版） |

显式参数优先于默认。

## 移交包增量（handoff.py）

```text
handoff/<world_id>/images/<asset_id>/<sha12>.png
```

仅带 reference_images 非空的资产；manifest items 逐图登记 sha256/bytes。
无图世界：images/ 目录可不出现，counts 增列 `images`（0 也显式标注）。

## 既有实体复用

- assets / asset_revisions（011：put_asset 自动升版留痕）
- worlds.config（本特性不涉及）

# Quickstart: 参考图生成验证

**Feature**: 013-reference-images | **Date**: 2026-10-21

## 离线验证（默认测试集，零外部调用）

```bash
uv run pytest -m "not real" -q
```

重点断言：

1. mock provider 全链：图片落 `images/<asset_id>/`、reference_images
   追加、资产修订 +1、image_generations 记录字段齐全。
2. 失败原子性：provider 抛错后目录零文件、资产字段不变、零生成记录。
3. BadPrompt：无 visual_prompt 且无 override 时报错指明缺口。
4. 宽高比默认：character → 2:3，scene → 16:9，显式优先。
5. 移交包：带图世界导出后 manifest 图片条目 sha256 与实算一致。

## 真机验收（real，SC-002）

前置：`.env` 已配 `MINIMAX_API_KEY`。

```bash
# 对 009 演示库的皇城司察子生成一张竖版参考图
uv run python -c "
from db.init_db import init as init_db
from orchestrator.store import Store
from orchestrator.images import generate_reference_images
init_db('yanyu.db')
s = Store('yanyu.db')
r = generate_reference_images(s, 'char_e8301d6530')
print(r['paths'], 'rev', r['revision'])
"
```

预期：`images/char_e8301d6530/<sha12>.png` 可打开；古装便服男子、
市井隐匿感与 visual_prompt 语义相符（人工核对）；`list_assets` 可见
reference_images 非空；`list_image_generations` 有记录。

## 故障验证

```bash
# 错误密钥
MINIMAX_API_KEY=sk-invalid uv run python -c "...同上..."
```

预期：ImageGenError 消息含图源 status_msg；目录零残留。

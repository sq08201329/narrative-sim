# Contract: 参考图生成（orchestrator/images.py + MCP）

**Feature**: 013-reference-images | **Date**: 2026-10-21

本契约先行于实现（宪章 I）。

## 1. 适配器协议

```python
# orchestrator/images.py

class ImageGenError(RuntimeError):
    """图源失败（鉴权/超时/审核拦截/回包畸形）；消息含图源 status_msg。"""

class ImageProvider(Protocol):
    name: str  # 图源标识，如 "minimax/image-01"
    def generate(self, prompt: str, n: int,
                 aspect_ratio: str) -> list[bytes]:
        """返回 n 张 PNG 字节；任何失败抛 ImageGenError，不返回部分结果。"""

class MinimaxImageProvider:
    """POST {MINIMAX_BASE_URL 或 https://api.minimaxi.com}/v1/image_generation
    model=image-01，response_format=base64；base_resp.status_code != 0 →
    ImageGenError(status_msg)；回包仅 image_urls 时 httpx 下载回退。
    缺 MINIMAX_API_KEY → ImageGenError 指明缺哪个键。"""
```

## 2. 生成入口

```python
def generate_reference_images(store: Store, asset_id: str,
                              n: int = 1,
                              aspect_ratio: str | None = None,
                              prompt_override: str | None = None,
                              provider: ImageProvider | None = None) -> dict:
    """单资产参考图生成（原子化，R4 次序）。

    - 资产不存在 → KeyError；无有效提示词（override 与 visual_prompt 均空）
      → ImageGenError("BadPrompt: ...")
    - 宽高比缺省按类型（data-model.md 表）
    - 成功：图片落 images/<asset_id>/<sha12>.png；reference_images 追加
      （put_asset 自动升版）；image_generations 落记录
    - 返回 {asset_id, paths, sha256, revision, prompt, n, aspect_ratio,
      provider}
    - 任何失败：零文件零字段残留
    """
```

## 3. MCP 工具

```python
def generate_reference_image(asset_id: str, n: int = 1,
                             aspect_ratio: str | None = None,
                             prompt_override: str | None = None) -> dict:
    """为资产生成参考图（MiniMax image-01，每张一次计费——宪章 VI）。
    返回 {asset_id, paths, revision, ...}。
    AssetNotFound / BadPrompt / ImageGenError。"""
```

## 4. store 原语

```python
def put_image_generation(asset_id: str, prompt: str, n: int,
                         aspect_ratio: str, paths: list[str],
                         sha256: list[str], provider: str,
                         asset_revision: int) -> int: ...
def list_image_generations(asset_id: str) -> list[dict]: ...
```

## 5. 移交包（handoff.py 增量）

export_handoff 增加：遍历世界资产 reference_images，复制图片到
`images/<asset_id>/`，manifest items 逐图登记；counts 增 `images` 键。

## 6. 测试契约

- `tests/contract/test_images.py`：mock provider（假 PNG 字节）驱动——
  落盘+登记+修订升版 / BadPrompt / 失败原子性（目录无文件、
  reference_images 不变、无生成记录）/ 宽高比默认 / prompt_override
  留痕 / 同内容去重同名。
- `test_handoff.py` 追加：带图移交 manifest 一致。
- `test_mcp_server.py` 追加：工具契约 + 错误词汇 + EXPECTED_TOOLS。
- 全部离线零外部调用；既有测试无回归。

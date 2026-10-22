"""参考图生成（013，宪章 II/IV/VI 接缝）。

- ImageProvider 协议 + MinimaxImageProvider（httpx 直调，base64 优先，
  image_urls 回退下载；base_resp.status_code != 0 → ImageGenError）
- generate_reference_images：原子次序 R4——取字节 → 校验 → 写盘 →
  put_asset（011 自动升版留痕）→ put_image_generation；失败零残留
- 密钥只经 MINIMAX_API_KEY 环境变量（.env），不落代码
"""
import base64
import hashlib
import os
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from .store import Store

load_dotenv()

_DEFAULT_RATIO = {"character": "2:3", "prop": "2:3",
                  "scene": "16:9", "epoch": "16:9"}


class ImageGenError(RuntimeError):
    """图源失败或提示词缺口（BadPrompt）；消息含图源 status_msg。"""


class ImageProvider(Protocol):
    name: str

    def generate(self, prompt: str, n: int,
                 aspect_ratio: str) -> list[bytes]:
        """返回 n 张 PNG 字节；任何失败抛 ImageGenError，不返回部分结果。"""
        ...


class MinimaxImageProvider:
    """MiniMax image-01 文生图（POST /v1/image_generation）。"""

    name = "minimax/image-01"

    def __init__(self, timeout: float = 120.0):
        self._timeout = timeout

    def generate(self, prompt: str, n: int,
                 aspect_ratio: str) -> list[bytes]:
        import httpx

        api_key = os.environ.get("MINIMAX_API_KEY")
        if not api_key:
            raise ImageGenError(
                "缺少环境变量 MINIMAX_API_KEY：请在 .env 中配置（013）")
        base = os.environ.get("MINIMAX_BASE_URL",
                              "https://api.minimaxi.com")
        resp = httpx.post(
            f"{base}/v1/image_generation",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "image-01", "prompt": prompt,
                  "aspect_ratio": aspect_ratio, "n": n,
                  "response_format": "base64"},
            timeout=self._timeout,
        )
        try:
            body = resp.json()
        except ValueError as e:
            raise ImageGenError(
                f"图源回包非 JSON（HTTP {resp.status_code}）") from e
        base_resp = body.get("base_resp") or {}
        if base_resp.get("status_code", 0) != 0:
            raise ImageGenError(
                f"图源拒绝（{base_resp.get('status_code')}）："
                f"{base_resp.get('status_msg', '无说明')}")
        data = body.get("data") or {}
        if data.get("image_base64"):
            return [base64.b64decode(b) for b in data["image_base64"][:n]]
        if data.get("image_urls"):
            out = []
            for url in data["image_urls"][:n]:
                r = httpx.get(url, timeout=self._timeout)
                r.raise_for_status()
                out.append(r.content)
            return out
        raise ImageGenError("图源回包无 image_base64/image_urls")


def generate_reference_images(store: Store, asset_id: str,
                              n: int = 1,
                              aspect_ratio: str | None = None,
                              prompt_override: str | None = None,
                              provider: ImageProvider | None = None) -> dict:
    """单资产参考图生成（原子化：失败零文件零字段零记录）。"""
    asset = store.get_asset(asset_id)  # KeyError 上抛
    prompt = (prompt_override
              or (asset.get("appearance") or {}).get("visual_prompt")
              or "").strip()
    if not prompt:
        raise ImageGenError(
            f"BadPrompt: 资产 {asset_id} 无 visual_prompt 且未给 override")
    ratio = aspect_ratio or _DEFAULT_RATIO.get(asset["type"], "1:1")
    provider = provider or MinimaxImageProvider()

    # R4 次序：先拿字节
    payloads = provider.generate(prompt, n, ratio)
    if not payloads or any(not p for p in payloads):
        raise ImageGenError("图源返回空图片")

    # 写盘（内容哈希命名：同内容去重，不同内容不覆盖）
    root = Path("images") / asset_id
    root.mkdir(parents=True, exist_ok=True)
    paths, hashes = [], []
    for p in payloads:
        digest = hashlib.sha256(p).hexdigest()
        fname = f"{digest[:12]}.png"
        fpath = root / fname
        if not fpath.exists():
            fpath.write_bytes(p)
        paths.append(f"images/{asset_id}/{fname}")
        hashes.append(digest)

    # 最后改库：只登记出图记录，**不碰资产 payload、不升修订**（A1）。
    # reference_images 由 Store.reference_images() 从 image_generations 派生。
    revision = store.current_revision(asset_id)
    store.put_image_generation(asset_id, prompt, len(paths), ratio,
                               paths, hashes, provider.name, revision)
    return {"asset_id": asset_id, "paths": paths, "sha256": hashes,
            "revision": revision, "prompt": prompt, "n": len(paths),
            "aspect_ratio": ratio, "provider": provider.name,
            "reference_images": store.reference_images(asset_id)}

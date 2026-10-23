"""参考图生成（013，宪章 II/IV/VI 接缝）。

- ImageProvider 协议 + MinimaxImageProvider（httpx 直调，base64 优先，
  image_urls 回退下载；base_resp.status_code != 0 → ImageGenError）
- generate_reference_images：原子次序 R4——取字节 → 校验 → 写盘 →
  put_asset（011 自动升版留痕）→ put_image_generation；失败零残留
- 密钥只经 MINIMAX_API_KEY 环境变量（.env），不落代码
"""
import base64
import hashlib
import mimetypes
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

    def generate(self, prompt: str, n: int, aspect_ratio: str,
                 subject_reference: str | None = None,
                 seed: int | None = None) -> list[bytes]:
        """返回 n 张 PNG 字节；任何失败抛 ImageGenError，不返回部分结果。

        subject_reference 传**已转换的 data URL**（由 _to_data_url 生成）；
        seed 为 None 表示不指定。
        """
        ...


_REF_MAX_BYTES = 10 * 1024 * 1024
# 魔数优先：图被改过名也不影响判型
_MAGIC_MIME = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def _to_data_url(ref: str) -> str:
    """主体参考图 → data URL（MiniMax image_file 接受 URL 或 base64 data URL）。

    - 已是 `data:` 开头则原样透传；
    - 文件不存在 / 超 10MB / 非 JPG-PNG 一律 ImageGenError；
    - 判型以**文件魔数**为准，扩展名只作 fallback；
    - 错误消息只回显路径，**绝不回显图片内容**。
    """
    if ref.startswith("data:"):
        return ref
    path = Path(ref)
    if not path.is_file():
        raise ImageGenError(f"参考图不存在：{ref}")
    raw = path.read_bytes()
    if len(raw) > _REF_MAX_BYTES:
        raise ImageGenError(f"参考图超过 10MB 上限：{ref}")
    mime = next((m for magic, m in _MAGIC_MIME if raw.startswith(magic)), None)
    if mime is None:
        mime = mimetypes.guess_type(path.name)[0]
    if mime not in ("image/jpeg", "image/png"):
        raise ImageGenError(
            f"参考图格式不支持（只收 JPG/PNG）：{ref}")
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


class MinimaxImageProvider:
    """MiniMax image-01 文生图 / 图生图（POST /v1/image_generation）。"""

    name = "minimax/image-01"

    def __init__(self, timeout: float = 180.0):
        self._timeout = timeout

    def generate(self, prompt: str, n: int, aspect_ratio: str,
                 subject_reference: str | None = None,
                 seed: int | None = None) -> list[bytes]:
        import httpx

        api_key = os.environ.get("MINIMAX_API_KEY")
        if not api_key:
            raise ImageGenError(
                "缺少环境变量 MINIMAX_API_KEY：请在 .env 中配置（013）")
        base = os.environ.get("MINIMAX_BASE_URL",
                              "https://api.minimaxi.com")
        payload = {"model": "image-01", "prompt": prompt,
                   "aspect_ratio": aspect_ratio, "n": n,
                   "response_format": "base64"}
        if subject_reference:
            # 官方：单张、type 只收 character、只锁主体长相，不锁服装/构图
            payload["subject_reference"] = [
                {"type": "character", "image_file": subject_reference}]
        if seed is not None:
            payload["seed"] = int(seed)
        resp = httpx.post(
            f"{base}/v1/image_generation",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=self._timeout,
        )
        if not (200 <= resp.status_code < 300):
            # 413（请求体过大）/ 401（鉴权）等直接给出状态码与截断正文；
            # 不回显 payload（含 data URL）与 key。
            raise ImageGenError(
                f"图源 HTTP {resp.status_code}：{(resp.text or '')[:200]}")
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
                              provider: ImageProvider | None = None,
                              subject_reference: str | None = None,
                              seed: int | None = None) -> dict:
    """单资产参考图生成（原子化：失败零文件零字段零记录）。

    subject_reference：本地图片路径或 data URL，锁主体长相（单张 JPG/PNG
    ≤10MB）；在调用 provider **之前**完成校验与转换，非法参考图不会发出请求。
    seed：同参数可复现。两者默认 None，行为与改动前一致。
    """
    asset = store.get_asset(asset_id)  # KeyError 上抛
    prompt = (prompt_override
              or (asset.get("appearance") or {}).get("visual_prompt")
              or "").strip()
    if not prompt:
        raise ImageGenError(
            f"BadPrompt: 资产 {asset_id} 无 visual_prompt 且未给 override")
    ratio = aspect_ratio or _DEFAULT_RATIO.get(asset["type"], "1:1")
    provider = provider or MinimaxImageProvider()
    # 先校验并转换参考图：错误在发起任何请求之前抛出（零计费）
    ref_data_url = _to_data_url(subject_reference) if subject_reference else None

    # R4 次序：先拿字节
    payloads = provider.generate(prompt, n, ratio,
                                 subject_reference=ref_data_url, seed=seed)
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
            "reference_images": store.reference_images(asset_id),
            "seed": seed, "used_reference": bool(ref_data_url)}

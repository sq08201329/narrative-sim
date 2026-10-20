"""003 US1-AC2 召回探针：不调用 LLM，验证语义记忆的存与取均经嵌入服务完成。

用法：先启动嵌入服务并在环境变量（或 .env）配置 EMBEDDING_API_BASE 等键位，然后

    uv run python scripts/probe_embedding_service.py

判定：写入 1 条「相关文档」+ 若干干扰文档，经查询前缀检索后，
相关文档余弦相似度必须高于所有干扰文档，否则退出码 1。
服务不可达 / 未配置环境变量 → 退出码 2。
"""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from orchestrator.embedding import (
    build_embedding_model,
    embedding_config,
    preflight_embedding,
)

RELATED = "公园里很多人在晨跑和遛狗，湖边有人打太极"
DISTRACTORS = [
    "量子力学的薛定谔方程描述了波函数演化",
    "明清两代的科举制度以八股取士",
    "番茄炒蛋先炒鸡蛋还是先炒番茄",
    "央行宣布下调存款准备金率零点五个百分点",
    "这部小说的主角在第三章离开了故乡",
]
QUERY = "户外运动的场景"


def cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb)


def main() -> int:
    load_dotenv()
    cfg = embedding_config()
    if cfg is None:
        print("未设置 EMBEDDING_API_BASE，无法探测（见 .env.example）")
        return 2
    reason = preflight_embedding(cfg)
    if reason is not None:
        print(f"预检失败: {reason}")
        return 2

    emb = build_embedding_model(cfg)
    q = emb.get_query_embedding(QUERY)
    scores = {}
    for name, doc in [("相关", RELATED)] + [(f"干扰{i+1}", d) for i, d in enumerate(DISTRACTORS)]:
        scores[name] = cos(q, emb.get_text_embedding(doc))

    for name, s in scores.items():
        print(f"query vs {name}: cos = {s:.4f}")

    best_distractor = max(s for n, s in scores.items() if n != "相关")
    if scores["相关"] <= best_distractor:
        print(f"FAIL: 相关文档 {scores['相关']:.4f} 未高于最佳干扰 {best_distractor:.4f}")
        return 1
    print(f"PASS: 相关文档 {scores['相关']:.4f} > 最佳干扰 {best_distractor:.4f}，语义召回有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())

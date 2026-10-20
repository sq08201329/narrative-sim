"""003 plan 探针：litert-lm 嵌入服务 + llama-index OpenAIEmbedding 兼容性实测。

验证三件事（结果写入 stdout，供 research.md 引用）：
1. OpenAIEmbedding 指向自定义端点（api_base + 自定义模型名 + 假 key）能否工作、维度
2. 客户端结果与裸 POST 是否一致（客户端无隐藏变换）
3. litert-lm 服务端是否自动添加 EmbeddingGemma 2 任务前缀
   （裸文本向量 vs 手工加前缀文本向量：若不同 → 服务端不加前缀，客户端需自行添加）
"""
import math

import httpx
from llama_index.embeddings.openai import OpenAIEmbedding

BASE = "http://127.0.0.1:9379/v1"
MODEL = "eg2-text-270m.litertlm"
DOC_PREFIX = "task: search result | text: "
QUERY_PREFIX = "task: search query | text: "

TEXT = "今天天气很好，适合出门散步"


def cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb)


def raw_embed(text):
    r = httpx.post(f"{BASE}/embeddings",
                   json={"model": MODEL, "input": text}, timeout=30)
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def main():
    # 注意：必须用 model_name= 而非 model= —— model= 会过 OpenAIEmbeddingModelType
    # 枚举白名单，自定义模型名直接被拒；model_name= 跳过白名单直接作为 engine。
    emb = OpenAIEmbedding(model_name=MODEL, api_base=BASE, api_key="dummy",
                          embed_batch_size=10, timeout=10.0, max_retries=1)
    v_client = emb.get_text_embedding(TEXT)
    v_raw = raw_embed(TEXT)
    v_raw_prefixed = raw_embed(DOC_PREFIX + TEXT)

    print(f"维度: {len(v_client)}")
    print(f"client vs raw      cos = {cos(v_client, v_raw):.6f}")
    print(f"raw vs raw+prefix  cos = {cos(v_client, v_raw_prefixed):.6f}")

    # 语义合理性：query 前缀检索是否能把相关文档排在无关文档之前
    docs = {
        "相关": "公园里很多人在晨跑和遛狗",
        "无关": "量子力学的薛定谔方程描述了波函数演化",
    }
    q = emb.get_query_embedding("户外运动的场景")
    q_prefixed = raw_embed(QUERY_PREFIX + "户外运动的场景")
    for name, d in docs.items():
        dv = raw_embed(DOC_PREFIX + d)
        print(f"query(无前缀)  vs doc[{name}] cos = {cos(q, dv):.4f}   "
              f"query(有前缀) vs doc[{name}] cos = {cos(q_prefixed, dv):.4f}")


if __name__ == "__main__":
    main()

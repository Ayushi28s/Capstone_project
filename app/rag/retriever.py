"""
Retrieval layer over the policy document Chroma collection.

Implements multi-query retrieval: the LLM proposes 2-3 reformulations of
the input question, each is embedded and searched independently, and
results are de-duplicated by chunk id. A customer asking "can I return
worn boots" and one asking "used footwear refund eligibility" should
both surface the same returns-policy chunk even though the wording
barely overlaps.
"""
import json

import chromadb
from chromadb.utils import embedding_functions
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.llm_client import router_llm

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL
        )
        _collection = _client.get_or_create_collection(
            name=settings.POLICY_COLLECTION, embedding_function=embed_fn
        )
    return _collection


def _expand_query(question: str, n_variants: int = 3) -> list[str]:
    """Ask the LLM for a few alternate phrasings. Falls back to just the
    original question if the model call fails — retrieval should degrade
    gracefully, not hard-fail the pipeline."""
    try:
        llm = router_llm()
        resp = llm.invoke([
            SystemMessage(content=(
                "You rewrite a customer-support question into alternate phrasings that a "
                "policy-document search engine might match better. "
                'Return ONLY a JSON array of strings, e.g. ["...", "..."]. '
                f"Produce at most {n_variants} variants, no preamble."
            )),
            HumanMessage(content=question),
        ])
        variants = json.loads(resp.content.strip().strip("`").removeprefix("json").strip())
        if isinstance(variants, list) and variants:
            return [question] + [str(v) for v in variants][:n_variants]
    except Exception:
        pass
    return [question]


def retrieve(question: str, top_k: int = None, multi_query: bool = True) -> list[dict]:
    """Return de-duplicated policy chunks relevant to `question`."""
    top_k = top_k or settings.RETRIEVER_TOP_K
    collection = _get_collection()
    queries = _expand_query(question) if multi_query else [question]

    seen_ids = set()
    results: list[dict] = []
    for q in queries:
        out = collection.query(query_texts=[q], n_results=top_k)
        ids = out.get("ids", [[]])[0]
        docs = out.get("documents", [[]])[0]
        metas = out.get("metadatas", [[]])[0]
        dists = out.get("distances", [[]])[0]
        for _id, doc, meta, dist in zip(ids, docs, metas, dists):
            if _id in seen_ids:
                continue
            seen_ids.add(_id)
            results.append({"id": _id, "text": doc, "source": meta.get("source"), "distance": dist})

    results.sort(key=lambda r: r["distance"])
    return results[: top_k * 2]


def format_context(chunks: list[dict]) -> str:
    return "\n\n---\n\n".join(f"[{c['source']}] {c['text']}" for c in chunks)

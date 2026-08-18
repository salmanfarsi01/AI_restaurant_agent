"""Small local-only test harness for the existing Qdrant index.

This is intentionally simpler than the Telegram/API flow:
- it reads the already-built local Qdrant index
- retrieves top-k relevant chunks for a query
- optionally uses a local LLM if one is already configured
- lets you switch between the four candidate models via MODEL_REGISTRY

Example:
    python -m app.local_rag_test "How much is Kachchi Biryani?" --k 4
    python -m app.local_rag_test "What is the price of Paneer?" --model qwen2.5-1.5b
"""
from __future__ import annotations

import argparse
from typing import Iterable

from app.config import MODEL_REGISTRY, settings
from app.models.llm_loader import get_llm
from app.rag.retriever import retrieve
from langchain_core.messages import HumanMessage


def _print_doc(doc: object, idx: int) -> None:
    metadata = getattr(doc, "metadata", {})
    source = metadata.get("source", "unknown")
    title = metadata.get("restaurant_name") or metadata.get("city") or "n/a"
    content = (getattr(doc, "page_content", "") or "").strip().replace("\n", " ")
    print(f"[{idx}] source={source} | restaurant={title}")
    print(content[:500])
    print("-" * 80)


def run_local_query(query: str, k: int = 4, model_key: str | None = None, use_llm: bool = False) -> dict:
    model_key = model_key or settings.selected_model
    model_cfg = settings.get_selected_model_config(model_key)

    if settings.llm_backend == "huggingface":
        print(f"Selected backend: huggingface")
        print(f"HF model: {settings.hf_llm_model}")
    else:
        print(f"Selected backend: ollama")
        print(f"Selected model: {model_key} ({model_cfg['label']})")
        print(f"Ollama model: {model_cfg.get('ollama_model', settings.ollama_model)}")
    print(f"Qdrant collection: {settings.qdrant_collection}")
    print(f"Query: {query}")
    print()

    docs = retrieve(query, k=k)
    print(f"Retrieved {len(docs)} document(s) from the local index.")
    for index, doc in enumerate(docs, start=1):
        _print_doc(doc, index)

    if use_llm:
        if settings.llm_backend == "huggingface":
            llm_model_name = settings.hf_llm_model
        else:
            llm_model_name = model_cfg.get("ollama_model") or settings.ollama_model
        llm = get_llm(model_name=llm_model_name)
        context = "\n\n".join(doc.page_content for doc in docs)
        prompt = (
            "Use only the context below to answer the user's question. "
            "If the answer is not present, say you do not know.\n\n"
            f"Context:\n{context}\n\nQuestion:\n{query}"
        )
        answer = llm.invoke([HumanMessage(content=prompt)]).content.strip()
        print("LLM answer:")
        print(answer)

    return {
        "model": model_key,
        "label": model_cfg["label"],
        "query": query,
        "documents": docs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the local Qdrant-backed RAG index without the Telegram API.")
    parser.add_argument("query", help="Question to test against the created index.")
    parser.add_argument("--k", type=int, default=4, help="Number of nearest-neighbor hits to retrieve")
    parser.add_argument("--model", choices=sorted(MODEL_REGISTRY.keys()), help="Model key from MODEL_REGISTRY to use for context")
    parser.add_argument("--use-llm", action="store_true", help="Optional: generate a final answer with the chosen local LLM backend if configured")
    args = parser.parse_args()

    run_local_query(args.query, k=args.k, model_key=args.model, use_llm=args.use_llm)


if __name__ == "__main__":
    main()

"""
Local, HuggingFace-based multilingual embedding model.
Swap EMBEDDING_MODEL in .env to benchmark different models for your paper,
e.g. intfloat/multilingual-e5-large, BAAI/bge-m3, jinaai/jina-embeddings-v3,
sentence-transformers/LaBSE, or a Bangla-specific model.
"""
from functools import lru_cache
from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings


@lru_cache(maxsize=4)
def get_embedding_model(model_name: str | None = None) -> HuggingFaceEmbeddings:
    """Cached loader so the same model isn't re-loaded into memory repeatedly."""
    name = model_name or settings.embedding_model
    return HuggingFaceEmbeddings(
        model_name=name,
        model_kwargs={"device": "cpu"},  # switch to "cuda" if you have a GPU
        encode_kwargs={"normalize_embeddings": True},
    )

"""
Local embedding model loader with resilient fallback for tests and development.
"""
from functools import lru_cache
from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=4)
def get_embedding_model(model_name: str | None = None):
    """Cached loader with fallback to FakeEmbeddings if PyTorch / HuggingFace is downloading."""
    name = model_name or settings.embedding_model
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name=name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception as e:
        log.warning("HuggingFaceEmbeddings not available (%s); using resilient FakeEmbeddings.", e)
        from langchain_core.embeddings import FakeEmbeddings
        return FakeEmbeddings(size=1024)

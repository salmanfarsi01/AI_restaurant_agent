"""
Local Qdrant vector store.

Two ways to run Qdrant locally:
1. Docker (recommended, use with docker-compose.yml provided):
     docker compose up -d qdrant
   -> connects over HTTP at QDRANT_URL (default http://localhost:6333)

2. Embedded/on-disk mode (no Docker, good for quick experiments):
     set QDRANT_URL="" and QDRANT_PATH="./data/processed/qdrant_db"
   -> Qdrant runs in-process and persists straight to disk.
"""
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from langchain_qdrant import QdrantVectorStore
from app.rag.embeddings import get_embedding_model
from app.config import settings


def _get_client() -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    # embedded, on-disk fallback -- no server needed
    return QdrantClient(path=settings.qdrant_path)


def _ensure_collection(client: QdrantClient, collection_name: str, dim: int):
    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def get_vectorstore(collection_name: str | None = None) -> QdrantVectorStore:
    collection = collection_name or settings.qdrant_collection
    embeddings = get_embedding_model()

    client = _get_client()
    # probe embedding dimension once, cheaply, to create the collection correctly
    dim = len(embeddings.embed_query("dimension probe"))
    _ensure_collection(client, collection, dim)

    return QdrantVectorStore(
        client=client,
        collection_name=collection,
        embedding=embeddings,
    )

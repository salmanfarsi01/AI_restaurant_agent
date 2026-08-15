"""
Thin wrapper around the vector store retriever, with optional metadata filters:
- lang: since only policy docs are truly bilingual (menu/restaurant docs are
  English-only, sourced from the CSV), pass lang=None when you want the
  Bangla query to still be able to pull English menu chunks (cross-lingual
  retrieval via the multilingual embedding model), and lang="bn"/"en" only
  when you specifically want to restrict to a language-tagged doc (policy).
- restaurant_name / city: narrow results to one restaurant or one city,
  useful once the agent knows which restaurant the user is ordering from.
"""
from langchain_core.documents import Document
from qdrant_client.http import models as qmodels
from app.rag.vectorstore import get_vectorstore


def _build_filter(lang: str | None, restaurant_name: str | None, city: str | None) -> qmodels.Filter | None:
    conditions = []
    if lang:
        conditions.append(qmodels.FieldCondition(key="metadata.lang", match=qmodels.MatchValue(value=lang)))
    if restaurant_name:
        conditions.append(
            qmodels.FieldCondition(key="metadata.restaurant_name", match=qmodels.MatchValue(value=restaurant_name))
        )
    if city:
        conditions.append(qmodels.FieldCondition(key="metadata.city", match=qmodels.MatchValue(value=city)))
    return qmodels.Filter(must=conditions) if conditions else None


def retrieve(
    query: str,
    lang: str | None = None,
    restaurant_name: str | None = None,
    city: str | None = None,
    k: int = 4,
) -> list[Document]:
    store = get_vectorstore()
    qfilter = _build_filter(lang, restaurant_name, city)
    return store.similarity_search(query, k=k, filter=qfilter)


def format_docs_for_prompt(docs: list[Document]) -> str:
    return "\n\n".join(f"[{d.metadata.get('source')}] {d.page_content}" for d in docs)

"""
Splits long documents (policy text) into retrieval-friendly chunks.
Menu items and restaurant-info docs (built from CSV rows in loader.py) are
already one atomic fact per doc, so they pass through unchanged -- splitting
a one-line "dish + price + description" doc would just hurt retrieval by
scattering the price away from the dish name.
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

_ATOMIC_SOURCES = {"menu", "restaurant_info"}

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=60,
    separators=["\n\n", "\n", "। ", ". ", " ", ""],  # includes Bangla sentence stop "।"
)


def split_documents(docs: list[Document]) -> list[Document]:
    chunked: list[Document] = []
    for doc in docs:
        if doc.metadata.get("source") in _ATOMIC_SOURCES:
            chunked.append(doc)
        else:
            chunked.extend(_splitter.split_documents([doc]))
    return chunked

"""
One-off script: load the menu CSV + bilingual policy text -> split -> embed
-> persist to Qdrant. Run this whenever data/raw/menu_dataset.csv or the
policy_*.txt files change:

    python -m app.rag.build_index

Uses data/raw/menu_dataset.csv if present (your real 5000-row export),
otherwise falls back to data/raw/menu_dataset_sample.csv for local testing.
"""
from app.rag.loader import load_all_documents
from app.rag.splitter import split_documents
from app.rag.vectorstore import get_vectorstore
from app.utils.logger import get_logger

log = get_logger(__name__)


def main():
    docs = load_all_documents()
    log.info(f"Loaded {len(docs)} raw documents")

    chunks = split_documents(docs)
    log.info(f"Split into {len(chunks)} chunks")

    store = get_vectorstore()

    # Qdrant accepts only integer IDs or UUIDs
    ids = list(range(len(chunks)))

    store.add_documents(chunks, ids=ids)
    log.info("Index built and persisted to Qdrant.")


if __name__ == "__main__":
    main()

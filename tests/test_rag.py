from app.config import MODEL_REGISTRY
from app.rag.loader import load_all_documents, load_menu_csv_documents, MENU_CSV_SAMPLE_PATH
from app.rag.splitter import split_documents


def test_model_registry_has_supported_local_models():
    assert set(MODEL_REGISTRY) == {
        "qwen2.5-0.5b",
        "qwen2.5-1.5b",
        "llama3.2-3b",
        "phi3.5-mini",
    }
    for config in MODEL_REGISTRY.values():
        assert {"repo_id", "filename", "label"}.issubset(config)


def test_load_menu_csv_dedupes_change_log():
    """
    Sample CSV has: a Created+Updated milk item (should survive with the
    latest price) and a Created-then-Deleted wing meal (should be dropped).
    """
    docs = load_menu_csv_documents(MENU_CSV_SAMPLE_PATH)
    menu_docs = [d for d in docs if d.metadata["source"] == "menu"]
    names = [d.metadata for d in menu_docs]

    milk = [d for d in menu_docs if "Milk" in d.page_content]
    assert len(milk) == 1
    assert milk[0].metadata["price"] == 2.29  # latest (Update) price, not the original 2.19

    wings = [d for d in menu_docs if "Boneless Wing" in d.page_content]
    assert len(wings) == 0  # latest event was Delete -> excluded


def test_load_menu_csv_builds_restaurant_docs():
    docs = load_menu_csv_documents(MENU_CSV_SAMPLE_PATH)
    restaurant_docs = [d for d in docs if d.metadata["source"] == "restaurant_info"]
    names = {d.metadata["restaurant_name"] for d in restaurant_docs}
    assert "Subway" in names


def test_load_all_documents_includes_bilingual_policy():
    docs = load_all_documents()
    policy_langs = {d.metadata["lang"] for d in docs if d.metadata["source"] == "policy"}
    assert {"en", "bn"} <= policy_langs


def test_split_documents_keeps_menu_and_restaurant_whole():
    docs = load_all_documents()
    chunks = split_documents(docs)
    atomic_before = [d for d in docs if d.metadata["source"] in ("menu", "restaurant_info")]
    atomic_after = [c for c in chunks if c.metadata["source"] in ("menu", "restaurant_info")]
    assert len(atomic_before) == len(atomic_after)

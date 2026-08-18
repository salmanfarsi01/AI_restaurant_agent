"""
Centralized app configuration, loaded from .env.

This project is being simplified for an agile local-only RAG flow first:
- use the existing Qdrant index on disk
- select one of the four local model presets below
- validate retrieval locally before adding agent / Telegram / evaluation layers
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

MODEL_REGISTRY = {
    "qwen2.5-0.5b": {
        "ollama_model": "qwen2.5:0.5b",
        "label": "Qwen2.5 0.5B",
    },
    "qwen2.5-1.5b": {
        "ollama_model": "qwen2.5:1.5b",
        "label": "Qwen2.5 1.5B",
    },
    "qwen3-0.6b": {
        "ollama_model": "qwen3:0.6b",
        "label": "Qwen3 0.6B",
    },
    "qwen3-1.7b": {
        "ollama_model": "qwen3:1.7b",
        "label": "Qwen3 1.7B",
    },
}


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = ""

    # Local-first model selection: keep simple until agent + Telegram are added.
    llm_backend: str = "ollama"
    selected_model: str = "qwen2.5-1.5b"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"

    # HuggingFace (used when llm_backend == "huggingface")
    hf_llm_model: str = "Qwen/Qwen3-8B"

    # Embeddings
    embedding_model: str = "intfloat/multilingual-e5-large"

    # Vector DB (Qdrant)
    qdrant_url: str = ""  # keep empty to use the local on-disk index already created
    qdrant_api_key: str = ""
    qdrant_path: str = "./data/processed/qdrant_storage"  # existing local index directory
    qdrant_collection: str = "restaurant_kb"

    # App DB
    database_url: str = "sqlite:///./data/processed/orders.db"

    # Misc
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def get_selected_model_config(self, model_name: str | None = None) -> dict:
        key = model_name or self.selected_model
        return MODEL_REGISTRY.get(key, MODEL_REGISTRY["qwen2.5-1.5b"])


settings = Settings()
"""
Centralized app configuration, loaded from .env
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = ""

    # LLM backend: "ollama" (talk to `ollama serve`) or "huggingface" (load
    # a transformers checkpoint directly into memory on this machine)
    llm_backend: str = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # HuggingFace (used when llm_backend == "huggingface")
    hf_llm_model: str = "Qwen/Qwen3-8B"

    # Embeddings
    embedding_model: str = "intfloat/multilingual-e5-large"

    # Vector DB (Qdrant)
    qdrant_url: str = "http://localhost:6333"   # set to "" to use embedded/on-disk mode instead
    qdrant_api_key: str = ""
    qdrant_path: str = "./data/processed/qdrant_db"  # used only when qdrant_url == ""
    qdrant_collection: str = "restaurant_kb"

    # App DB
    database_url: str = "sqlite:///./data/processed/orders.db"

    # Misc
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
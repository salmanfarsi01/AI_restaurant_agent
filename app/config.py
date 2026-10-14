"""
Centralized app configuration loaded from environment / .env.
Supports Groq LLM, SQLite ground-truth DB, Email verification,
Thermal POS printing, Google Sheets sync, and Telegram.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Server & Core Security ---
    app_env: str = "development"
    server_base_url: str = "http://localhost:8000"
    secret_key: str = "super_secret_restaurant_key_change_me_in_prod"
    admin_api_key: str = "admin_secret_token_12345"
    token_expiry_minutes: int = 45

    # --- LLM Engine (Groq default) ---
    llm_backend: str = "groq"  # "groq" | "ollama" | "huggingface"
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"
    groq_fast_model: str = "qwen/qwen3.8-27b"

    # --- Ollama / Local fallback ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"
    selected_model: str = "qwen2.5-1.5b"

    # --- Embeddings & Vector DB (Qdrant) ---
    embedding_model: str = "intfloat/multilingual-e5-large"
    qdrant_url: str = ""  # empty = local disk mode
    qdrant_api_key: str = ""
    qdrant_path: str = "./data/processed/qdrant_storage"
    qdrant_collection: str = "restaurant_kb"

    # --- Database (SQLite Ground Truth) ---
    database_url: str = "sqlite:///./data/processed/orders.db"

    # --- Email & SMTP (Verification & Marketing) ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "orders@dhakaspicehouse.com"
    smtp_from_name: str = "Dhaka Spice House"
    smtp_use_tls: bool = True
    smtp_mock_mode: bool = True  # True = saves HTML email to data/emails/ when SMTP is unconfigured
    emails_dir: str = "./data/emails"

    # --- Kitchen Thermal POS Printer ---
    printer_mode: str = "mock"  # "mock" | "network" | "windows"
    printer_ip: str = "192.168.1.200"
    printer_port: int = 9100
    printer_windows_name: str = "POS-80"
    receipts_dir: str = "./data/receipts"

    # --- Google Sheets CRM & Reporting ---
    google_sheets_enabled: bool = True
    google_service_account_file: str = "./credentials.json"
    google_sheet_title: str = "Dhaka Spice House Orders & Leads"
    google_sheet_id: str = "1m-xdTMn0B6ATc0PxRkApDBq6YPzuC6X9DCvcDJBlPdk"
    sheets_backup_dir: str = "./data/sheets_backup"

    # --- Telegram Bot ---
    telegram_bot_token: str = ""

    # --- Restaurant Defaults ---
    restaurant_name: str = "Dhaka Spice House"
    restaurant_phone: str = "+880 1700-000000"
    restaurant_address: str = "House 42, Road 11, Banani, Dhaka"
    delivery_fee: float = 60.0

    # --- Logging ---
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def ensure_directories(self) -> None:
        """Create required local data directories if they do not exist."""
        for path_str in [
            "./data/processed",
            self.emails_dir,
            self.receipts_dir,
            self.sheets_backup_dir,
        ]:
            Path(path_str).mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
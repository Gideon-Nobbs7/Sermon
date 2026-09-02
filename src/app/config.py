from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration from environment and `.env`."""

    app_env: str = "development"
    log_level: str = "INFO"

    sqlite_db_path: Path = Path("./data/sermons.db")

    data_dir: Path = Path("./data")
    sermon_file_path: Path = Path("./data/2026-Sermons.md")

    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    llm_base_url: str
    llm_model: str
    llm_api_key: str = ""

    openai_api_key: str = ""

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

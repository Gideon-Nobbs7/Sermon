from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration from environment and `.env`."""

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    SQLITE_DB_PATH: Path = Path("./data/sermons.db")

    DATA_DIR: Path = Path("./data")
    SERMON_FILE_PATH: Path = Path("./data/2026-Sermons.md")

    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    OPENAI_EMBEDDINGS_URL: str = "https://api.openai.com/v1/embeddings"

    LLM_BASE_URL: str
    LLM_MODEL: str
    LLM_API_KEY: str = ""

    OPENAI_API_KEY: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    TELEGRAM_SECRET_HEADER: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

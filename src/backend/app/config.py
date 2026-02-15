"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration — loaded from environment / .env file."""

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "aura_user"
    postgres_password: str = "aura_secret_password"
    postgres_db: str = "knowledge_assistant"

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379

    # --- LLM ---
    llm_provider: str = "stub"  # "openai" | "stub"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- Embeddings ---
    embedding_provider: str = "stub"  # "openai" | "stub"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 384

    # --- App ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"

    # --- Cache ---
    cache_ttl_seconds: int = 3600

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

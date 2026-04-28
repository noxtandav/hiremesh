from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "test", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://hiremesh:hiremesh@localhost:5432/hiremesh"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = Field(default="dev-only-change-me-in-prod", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 60 * 60 * 24

    cookie_name: str = "hiremesh_session"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Admin"

    # Object storage (MinIO in dev, R2 in prod).
    s3_endpoint: str = "http://minio:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio12345"
    s3_bucket: str = "hiremesh"
    s3_region: str = "us-east-1"

    # LLM. `fake` makes the parser produce deterministic dummy data without
    # calling any model — for dev/tests without an API key.
    llm_parse_model: str = "fake"
    llm_embed_model: str = "fake"
    # Used by Q&A: per-candidate synthesis, pool classifier, SQL generation,
    # final answer composition. One env var covers all four roles for now —
    # split per-role only if perf demands it later.
    llm_qa_model: str = "fake"
    llm_api_key: str | None = None

    # Vector dim of the chosen embedding model. Must match what the model
    # returns. Common values: 1536 (text-embedding-3-small, openai/ada-002),
    # 3072 (text-embedding-3-large), 1024 (voyage-3-large, cohere/embed-v3),
    # 768 (nomic-embed-text). Changing this requires resetting the
    # candidate_embeddings table — see docs/search-and-ask.md.
    llm_embed_dim: int = 1536


@lru_cache
def get_settings() -> Settings:
    return Settings()

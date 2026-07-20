from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "YouTube AI Knowledge Base"
    database_url: str = (
        "postgresql+psycopg://postgres:password@localhost:5432/youtube_kb"
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "youtube_video_chunks"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384

    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = None

    chunk_size_segments: int = 10
    chunk_overlap_segments: int = 2

    data_dir: str = "/tmp/youtube-ai-knowledge-base/videos"
    model_cache_dir: str = "/tmp/youtube-ai-knowledge-base/models"

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

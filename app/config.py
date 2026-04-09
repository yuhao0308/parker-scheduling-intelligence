from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://parker:parker@localhost:5432/parker_scheduling"

    # Ollama (local LLM)
    ollama_model: str = "qwen3.5:9b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout: int = 10
    ollama_temperature: float = 0.3

    # Scoring
    scoring_weights_path: Path = Path("config/scoring_weights.yaml")

    # Application
    log_level: str = "INFO"
    max_candidates_returned: int = 10
    shadow_mode: bool = False

    # Facility
    facility_zip_code: str = "11375"


settings = Settings()
